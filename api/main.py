import json
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from google.adk.events import Event, EventActions
from google.adk.sessions import DatabaseSessionService
from pydantic import BaseModel, ConfigDict, Field

from agents.bug_assistant.config import BugSettings
from agents.bug_assistant.mcp import McpUnavailable
from agents.bug_assistant.models import (
    BugTriageRequest,
    CreatedIssue,
    ProposedIssue,
    VerifiedTriage,
)
from agents.bug_assistant.run import PipelineError as BugPipelineError
from agents.bug_assistant.run import ProviderBlocked as BugProviderBlocked
from agents.bug_assistant.run import run_triage
from agents.bug_assistant.writes import (
    GRANT_TTL_SECONDS,
    STATE_KEY,
    ApprovalGrant,
    ApprovalRequired,
    authorize,
    create_issue,
    mint_grant,
)
from agents.gemini_cli_tool.models import CliAnswer, CliPlan, CliRequest, GroundingCheck
from agents.gemini_cli_tool.run import PipelineError as CliPipelineError
from agents.gemini_cli_tool.run import ProviderBlocked as CliProviderBlocked
from agents.gemini_cli_tool.run import run_cli_pipeline
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


class StageView(BaseModel):
    """One observable step. `kind` distinguishes an ADK model call, a deterministic
    ADK stage and the Gemini CLI subprocess, which is the point of Part B."""

    name: str
    kind: str
    outcome: str
    detail: str


class ApprovalOffer(BaseModel):
    """An offer to write, not a permission. Spending it requires presenting it back
    alongside the unchanged content it was minted for."""

    approval_token: str
    content_sha256: str
    repository: str
    expires_in_seconds: int
    write_path_blocked_by: list[str]


class IssueWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_token: str = Field(min_length=16, max_length=256)
    proposed_issue: ProposedIssue


class TriageResponse(BaseModel):
    triage: VerifiedTriage
    proposed_issue: ProposedIssue | None
    approval: ApprovalOffer | None
    stages: list[StageView]
    mcp_actually_used: bool
    usage: UsageView


class CliInspectResponse(BaseModel):
    answer: CliAnswer
    grounding: GroundingCheck
    plan: CliPlan | None
    stages: list[StageView]
    cli_invocation: dict[str, Any] | None
    cli_actually_ran: bool
    usage: UsageView


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

    async def remember(
        agent: AgentName, session_id: str, subject: str, delta: dict[str, Any]
    ) -> None:
        """Persist a state change outside a runner, e.g. an approval grant."""
        session = await sessions.get_session(app_name=agent, user_id=subject, session_id=session_id)
        if session is None:
            raise HTTPException(404, "Session not found")
        await sessions.append_event(
            session,
            Event(
                author="api",
                invocation_id=str(uuid.uuid4()),
                actions=EventActions(state_delta=delta),
            ),
        )

    @application.post(
        "/api/agents/bug_assistant/{session_id}/triage", response_model=TriageResponse
    )
    async def triage(
        session_id: uuid.UUID,
        body: BugTriageRequest,
        user: Annotated[Identity, Depends(identity)],
    ) -> TriageResponse:
        """Read-only triage. Offers an approval for a write but grants nothing."""
        await get_session("bug_assistant", session_id, user)
        started = time.monotonic()
        try:
            verified, draft, trace = await run_triage(
                body,
                session_service=sessions,
                user_id=user.subject,
                session_id=str(session_id),
            )
        except BugProviderBlocked as exc:
            raise HTTPException(503, str(exc)) from exc
        except BugPipelineError as exc:
            raise HTTPException(502, str(exc)) from exc

        grant = None
        write_blocked = BugSettings().write_missing()
        if draft is not None:
            try:
                minted = mint_grant(draft, user.subject)
            except McpUnavailable as exc:
                raise HTTPException(409, str(exc)) from exc
            await remember(
                "bug_assistant", str(session_id), user.subject, {STATE_KEY: minted.as_dict()}
            )
            grant = ApprovalOffer(
                approval_token=minted.token,
                content_sha256=minted.content_sha256,
                repository=minted.repository,
                expires_in_seconds=int(GRANT_TTL_SECONDS),
                write_path_blocked_by=write_blocked,
            )
        logger.info(
            json.dumps(
                {
                    "agent": "bug_assistant",
                    "session": str(session_id),
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "mcp_used": trace.mcp_actually_used,
                    "issues_searched": verified.issues_searched,
                    "verified_duplicates": len(verified.verified_duplicates),
                }
            )
        )
        return TriageResponse(
            triage=verified,
            proposed_issue=draft,
            approval=grant,
            stages=[
                StageView(name=s.name, kind=s.kind, outcome=s.outcome, detail=s.detail)
                for s in trace.stages
            ],
            mcp_actually_used=trace.mcp_actually_used,
            usage=UsageView(
                prompt_tokens=trace.prompt_tokens,
                output_tokens=trace.output_tokens,
                thought_tokens=trace.thought_tokens,
                billable_searches=0,
            ),
        )

    @application.post(
        "/api/agents/bug_assistant/{session_id}/create-issue", response_model=CreatedIssue
    )
    async def create_issue_route(
        session_id: uuid.UUID,
        body: IssueWriteRequest,
        user: Annotated[Identity, Depends(identity)],
    ) -> CreatedIssue:
        """The only mutating route in the suite. Requires a matching approval grant."""
        session = await sessions.get_session(
            app_name="bug_assistant", user_id=user.subject, session_id=str(session_id)
        )
        if session is None:
            raise HTTPException(404, "Session not found")
        stored = session.state.get(STATE_KEY)
        grant = ApprovalGrant.from_dict(stored) if isinstance(stored, dict) else None
        try:
            authorize(grant, body.approval_token, body.proposed_issue, user.subject)
        except ApprovalRequired as exc:
            raise HTTPException(403, str(exc)) from exc
        assert grant is not None  # authorize() rejects None before this point
        # Burn the grant before the write, so a failed attempt cannot be retried blind.
        grant.used = True
        await remember("bug_assistant", str(session_id), user.subject, {STATE_KEY: grant.as_dict()})
        try:
            created = await create_issue(body.proposed_issue)
        except ApprovalRequired as exc:
            raise HTTPException(409, str(exc)) from exc
        except McpUnavailable as exc:
            raise HTTPException(502, str(exc)) from exc
        logger.info(
            json.dumps(
                {
                    "agent": "bug_assistant",
                    "session": str(session_id),
                    "action": "issue_created",
                    "number": created.number,
                }
            )
        )
        return created

    @application.post(
        "/api/agents/gemini_cli_tool/{session_id}/inspect", response_model=CliInspectResponse
    )
    async def inspect(
        session_id: uuid.UUID, body: CliRequest, user: Annotated[Identity, Depends(identity)]
    ) -> CliInspectResponse:
        """Plan in ADK, inspect with the real CLI subprocess, verify deterministically."""
        await get_session("gemini_cli_tool", session_id, user)
        started = time.monotonic()
        try:
            answer, grounding, plan, trace = await run_cli_pipeline(
                body.question,
                session_service=sessions,
                user_id=user.subject,
                session_id=str(session_id),
            )
        except CliProviderBlocked as exc:
            raise HTTPException(503, str(exc)) from exc
        except CliPipelineError as exc:
            raise HTTPException(502, str(exc)) from exc
        logger.info(
            json.dumps(
                {
                    "agent": "gemini_cli_tool",
                    "session": str(session_id),
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "cli_actually_ran": trace.cli_actually_ran,
                    "grounded": grounding.grounded,
                }
            )
        )
        return CliInspectResponse(
            answer=answer,
            grounding=grounding,
            plan=plan,
            stages=[
                StageView(
                    name=stage.name, kind=stage.kind, outcome=stage.outcome, detail=stage.detail
                )
                for stage in trace.stages
            ],
            cli_invocation=trace.cli_invocation,
            cli_actually_ran=trace.cli_actually_ran,
            usage=UsageView(
                prompt_tokens=trace.prompt_tokens,
                output_tokens=trace.output_tokens,
                thought_tokens=trace.thought_tokens,
                billable_searches=0,
            ),
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
