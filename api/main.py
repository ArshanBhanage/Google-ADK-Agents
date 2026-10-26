import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from google.adk.sessions import DatabaseSessionService
from pydantic import BaseModel, ConfigDict

from packages.agent_core.auth import Identity, authenticate
from packages.agent_core.config import AGENTS, Settings

logger = logging.getLogger("adk_suite")
AgentName = Literal[
    "lead_research", "gemini_cli_tool", "bug_assistant", "code_reviewer", "ecommerce"
]


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent: AgentName


class SessionResponse(BaseModel):
    id: str
    agent: str


class AgentStatus(BaseModel):
    id: str
    name: str
    status: str


class Readiness(BaseModel):
    status: str
    authentication: str
    missing: list[str]
    gemini: str
    agents: list[AgentStatus]


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    sessions = DatabaseSessionService(db_url=config.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await sessions.close()

    application = FastAPI(title="ADK Agent Suite", lifespan=lifespan)

    @application.middleware("http")
    async def correlation(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        correlation_id = str(uuid.uuid4())
        started = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = correlation_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        logger.info(
            json.dumps(
                {
                    "request_id": correlation_id,
                    "method": request.method,
                    "status": response.status_code,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                }
            )
        )
        return response

    async def identity(authorization: Annotated[str | None, Header()] = None) -> Identity:
        return await authenticate(authorization, config)

    @application.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "alive"}

    @application.get("/api/readiness", response_model=Readiness)
    async def readiness(response: Response) -> Readiness:
        missing = config.auth_missing()
        if not config.google_api_key.get_secret_value():
            missing.append("GOOGLE_API_KEY")
        if not config.gemini_model:
            missing.append("GEMINI_MODEL")
        response.status_code = 503
        return Readiness(
            status="BLOCKED" if missing else "NOT_STARTED",
            authentication="BLOCKED" if config.auth_missing() else "CONFIGURED_NOT_VERIFIED",
            missing=missing,
            gemini="BLOCKED" if "GOOGLE_API_KEY" in missing else "CONFIGURED_NOT_VERIFIED",
            agents=[
                AgentStatus(id=key, name=value, status="NOT_STARTED")
                for key, value in AGENTS.items()
            ],
        )

    @application.post("/api/sessions", response_model=SessionResponse, status_code=201)
    async def create_session(
        body: SessionRequest, user: Annotated[Identity, Depends(identity)]
    ) -> SessionResponse:
        session = await sessions.create_session(app_name=body.agent, user_id=user.subject)
        return SessionResponse(id=session.id, agent=body.agent)

    @application.get("/api/sessions/{agent}/{session_id}", response_model=SessionResponse)
    async def get_session(
        agent: AgentName, session_id: uuid.UUID, user: Annotated[Identity, Depends(identity)]
    ) -> SessionResponse:
        session = await sessions.get_session(
            app_name=agent, user_id=user.subject, session_id=str(session_id)
        )
        if session is None:
            raise HTTPException(404, "Session not found")
        return SessionResponse(id=session.id, agent=agent)

    @application.delete("/api/sessions/{agent}/{session_id}", status_code=204)
    async def delete_session(
        agent: AgentName, session_id: uuid.UUID, user: Annotated[Identity, Depends(identity)]
    ) -> Response:
        await get_session(agent, session_id, user)
        await sessions.delete_session(
            app_name=agent, user_id=user.subject, session_id=str(session_id)
        )
        return Response(status_code=204)

    return application


app = create_app()
