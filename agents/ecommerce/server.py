"""Standalone Part E API and storefront, bound to loopback by the launch command."""

import asyncio
import secrets
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.agents.run_config import RunConfig
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from .agent import build_agent
from .auth import authenticate
from .commerce import Commerce, CommerceError
from .config import COMPONENT, CommerceSettings
from .mcp_client import call_catalog
from .models import Action, Chat
from .shopify import ShopifyUnavailable


def create_app() -> FastAPI:
    settings = CommerceSettings()
    commerce = Commerce(settings)
    # SQLAlchemy's psycopg dialect supports the async session backend.
    sessions = DatabaseSessionService(
        db_url=settings.database_url.get_secret_value().replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    )
    model_slots = asyncio.Semaphore(2)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await sessions.close()

    app = FastAPI(title="Part E · Shopify Commerce", lifespan=lifespan)

    @app.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.headers.get("host", "").split(":")[0] not in {"127.0.0.1", "localhost"}:
            return JSONResponse({"detail": "Local access only"}, status_code=403)
        if request.method == "POST" and request.headers.get("origin") not in {
            None,
            "http://127.0.0.1:8085",
            "http://localhost:8085",
        }:
            return JSONResponse({"detail": "Origin denied"}, status_code=403)
        if int(request.headers.get("content-length", "0")) > 16384:
            return JSONResponse({"detail": "Request too large"}, status_code=413)
        try:
            response = await call_next(request)
        except Exception:
            # Never return upstream tracebacks, SQL parameters or cart secrets.
            response = JSONResponse({"detail": "SERVICE_UNAVAILABLE"}, status_code=503)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' https:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        return response

    async def identity(authorization: Annotated[str | None, Header()] = None) -> str:
        return await authenticate(authorization, settings)

    User = Annotated[str, Depends(identity)]

    @app.exception_handler(CommerceError)
    async def commerce_error(_: Request, exc: CommerceError) -> JSONResponse:
        return JSONResponse({"detail": exc.code}, status_code=exc.status)

    @app.exception_handler(ShopifyUnavailable)
    async def shopify_error(_: Request, exc: ShopifyUnavailable) -> JSONResponse:
        return JSONResponse(
            {"detail": "SHOPIFY_UNAVAILABLE: refresh cart before retrying"}, status_code=502
        )

    @app.get("/api/me")
    async def me(user: User) -> dict[str, str]:
        return {"status": "authenticated", "mode": "local_per_user_token"}

    @app.get("/api/catalog")
    async def catalog(user: User, query: str = "") -> dict[str, Any]:
        if not 1 <= len(query) <= 300:
            raise HTTPException(422, "Enter 1–300 search characters")
        return await call_catalog(settings, "search_catalog", {"query": query})

    @app.get("/api/availability")
    async def availability(user: User, variant_id: str) -> dict[str, Any]:
        if not variant_id.startswith("gid://shopify/ProductVariant/") or len(variant_id) > 100:
            raise HTTPException(422, "Invalid variant")
        return await commerce.availability(variant_id)

    @app.get("/api/cart")
    async def cart(user: User, cart_id: uuid.UUID | None = None) -> dict[str, Any]:
        return await commerce.view(user, str(cart_id) if cart_id else None)

    @app.post("/api/cart/actions")
    async def act(body: Action, user: User) -> dict[str, Any]:
        payload = body.model_dump(mode="json", exclude={"request_id", "action", "confirmed"})
        return await commerce.action(user, body.request_id, body.action, payload)

    @app.get("/api/orders")
    async def orders(user: User) -> dict[str, str]:
        return {
            "status": "BLOCKED",
            "reason": "Shopify customer-account authorization is not configured.",
        }

    @app.post("/api/chat")
    async def chat(body: Chat, user: User) -> dict[str, Any]:
        if model_slots.locked():
            raise HTTPException(429, "Agent busy; retry shortly")
        async with model_slots, asyncio.timeout(90):
            agent = build_agent(settings, user)
            session = await sessions.create_session(
                app_name="ecommerce", user_id=user, session_id=secrets.token_hex(16)
            )
            runner = Runner(agent=agent, app_name="ecommerce", session_service=sessions)
            trace: list[str] = []
            answer = ""
            try:
                async for event in runner.run_async(
                    user_id=user,
                    session_id=session.id,
                    run_config=RunConfig(max_llm_calls=6),
                    new_message=types.Content(role="user", parts=[types.Part(text=body.message)]),
                ):
                    trace.extend(call.name or "tool" for call in event.get_function_calls())
                    if event.is_final_response() and event.content:
                        answer = "\n".join(part.text or "" for part in event.content.parts or [])
            except LlmCallsLimitExceededError:
                answer = (
                    "I reached the search limit before finding a useful recommendation. "
                    "What type of product are you looking for, and what is your budget?"
                )
            finally:
                for tool in agent.tools:
                    if hasattr(tool, "close"):
                        await tool.close()
            return {"answer": answer, "tools": trace, "session_id": session.id}

    if (COMPONENT / "web/dist").exists():
        app.mount("/", StaticFiles(directory=COMPONENT / "web/dist", html=True), name="storefront")
    return app


app = create_app()
