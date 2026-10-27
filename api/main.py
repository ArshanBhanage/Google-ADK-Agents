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

from agents.lead_research.export import report_to_csv
from agents.lead_research.models import LeadReport, ResearchRequest
from agents.lead_research.run import PipelineError, ProviderBlocked, run_research
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


class ToolCallView(BaseModel):
    agent: str
    tool: str
    outcome: str


class UsageView(BaseModel):
    prompt_tokens: int
    output_tokens: int
    thought_tokens: int
    billable_searches: int


class ResearchResponse(BaseModel):
    """Observable evidence of the run. Carries no credentials and no model reasoning."""

    report: LeadReport
    searches: list[str]
    grounding_sources: list[str]
    search_suggestions: list[str]
    tool_calls: list[ToolCallView]
    retrieved_sources: list[str]
    model_versions: list[str]
    usage: UsageView


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
        missing = config.auth_missing() + config.provider_missing()
        # Configuration completeness is not provider entitlement; only `make probe-lead`
        # establishes that, so the reported state stops at CONFIGURED_NOT_VERIFIED.
        if missing:
            response.status_code = 503
        return Readiness(
            status="BLOCKED" if missing else "CONFIGURED_NOT_VERIFIED",
            authentication="BLOCKED" if config.auth_missing() else "CONFIGURED_NOT_VERIFIED",
            missing=missing,
            gemini="BLOCKED" if config.provider_missing() else "CONFIGURED_NOT_VERIFIED",
            agents=[
                AgentStatus(
                    id=key,
                    name=value,
                    status="READY"
                    if key == "lead_research" and not missing
                    else "BLOCKED_CONFIGURATION"
                    if key == "lead_research"
                    else "NOT_STARTED",
                )
                for key, value in AGENTS.items()
            ],
        )

    @application.post(
        "/api/agents/lead_research/{session_id}/research", response_model=ResearchResponse
    )
    async def research(
        session_id: uuid.UUID,
        body: ResearchRequest,
        user: Annotated[Identity, Depends(identity)],
        response: Response,
    ) -> ResearchResponse:
        """Run the lead pipeline inside the caller's own session. Read-only externally."""
        await get_session("lead_research", session_id, user)
        started = time.monotonic()
        try:
            report, trace = await run_research(
                body,
                session_service=sessions,
                user_id=user.subject,
                session_id=str(session_id),
            )
        except ProviderBlocked as exc:
            # A provider refusal is reported as a dependency failure, never as an
            # empty result that a reader could mistake for "no leads found".
            raise HTTPException(503, str(exc)) from exc
        except PipelineError as exc:
            raise HTTPException(502, str(exc)) from exc
        logger.info(
            json.dumps(
                {
                    "agent": "lead_research",
                    "session": str(session_id),
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "searches": trace.billable_searches,
                    "retrieved": len(trace.retrieved_sources),
                    "verified_leads": len(report.leads),
                }
            )
        )
        response.headers["X-Billable-Searches"] = str(trace.billable_searches)
        return ResearchResponse(
            report=report,
            searches=trace.search_queries,
            grounding_sources=trace.grounding_sources,
            search_suggestions=trace.search_entry_points,
            tool_calls=[
                ToolCallView(agent=call.agent, tool=call.tool, outcome=call.outcome)
                for call in trace.tool_invocations
            ],
            retrieved_sources=trace.retrieved_sources,
            model_versions=trace.model_versions,
            usage=UsageView(
                prompt_tokens=trace.prompt_tokens,
                output_tokens=trace.output_tokens,
                thought_tokens=trace.thought_tokens,
                billable_searches=trace.billable_searches,
            ),
        )

    @application.get("/api/agents/lead_research/{session_id}/export.csv")
    async def export_csv(
        session_id: uuid.UUID, user: Annotated[Identity, Depends(identity)]
    ) -> Response:
        """Serve the CSV from the persisted report so it cannot differ from the UI."""
        session = await sessions.get_session(
            app_name="lead_research", user_id=user.subject, session_id=str(session_id)
        )
        if session is None:
            raise HTTPException(404, "Session not found")
        stored = session.state.get("lead_report")
        if stored is None:
            raise HTTPException(409, "No completed research in this session yet")
        body = report_to_csv(LeadReport.model_validate(stored))
        return Response(
            content=body,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="leads-{session_id}.csv"',
                "Cache-Control": "no-store",
            },
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
