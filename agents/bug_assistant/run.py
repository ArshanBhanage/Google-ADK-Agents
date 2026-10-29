import uuid
from dataclasses import dataclass, field
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.genai import errors, types

from agents.bug_assistant.agent import build_pipeline
from agents.bug_assistant.models import BugTriageRequest, ProposedIssue, VerifiedTriage
from packages.agent_core.provider import resolve_backend

APP_NAME = "bug_assistant"


class PipelineError(RuntimeError):
    """The pipeline produced no verified triage."""


class ProviderBlocked(PipelineError):
    """A provider capability the pipeline depends on is unavailable."""


QUOTA_GUIDANCE = (
    "BLOCKED_PROVIDER_QUOTA: the Gemini API returned 429 RESOURCE_EXHAUSTED after the "
    "configured retries. No triage is substituted."
)

STAGE_KINDS = {
    "issue_triage": "adk_llm_agent",
    "issue_verifier": "adk_deterministic_agent",
    "issue_drafter": "adk_llm_agent",
}


@dataclass
class Stage:
    name: str
    kind: str
    outcome: str
    detail: str = ""


@dataclass
class BugTrace:
    invocation_id: str
    events: int = 0
    stages: list[Stage] = field(default_factory=list)
    mcp_calls: list[str] = field(default_factory=list)
    prompt_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0

    @property
    def mcp_actually_used(self) -> bool:
        return bool(self.mcp_calls)

    def as_dict(self) -> dict[str, Any]:
        return {
            "invocation_id": self.invocation_id,
            "events": self.events,
            "mcp_actually_used": self.mcp_actually_used,
            "stages": [vars(stage) for stage in self.stages],
            "mcp_calls": self.mcp_calls,
            "usage": {
                "prompt_tokens": self.prompt_tokens,
                "output_tokens": self.output_tokens,
                "thought_tokens": self.thought_tokens,
            },
        }


def _collect(event: Any, trace: BugTrace) -> None:
    usage = event.usage_metadata
    if usage:
        trace.prompt_tokens += usage.prompt_token_count or 0
        trace.output_tokens += usage.candidates_token_count or 0
        trace.thought_tokens += usage.thoughts_token_count or 0
    kind = STAGE_KINDS.get(event.author)
    if kind and not any(stage.name == event.author for stage in trace.stages):
        trace.stages.append(Stage(name=event.author, kind=kind, outcome="ran"))
    for part in event.content.parts if event.content and event.content.parts else []:
        if part.function_call:
            trace.mcp_calls.append(part.function_call.name)
            trace.stages.append(
                Stage(name=part.function_call.name, kind="mcp_tool_call", outcome="called")
            )
        if part.function_response:
            response = part.function_response.response
            status = (
                response.get("status", "returned") if isinstance(response, dict) else "returned"
            )
            detail = ""
            if isinstance(response, dict):
                detail = str(response.get("reason") or f"returned={response.get('returned', '')}")
            trace.stages.append(
                Stage(
                    name=part.function_response.name,
                    kind="mcp_tool_call",
                    outcome=str(status),
                    detail=detail[:300],
                )
            )


async def run_triage(
    request: BugTriageRequest,
    *,
    session_service: BaseSessionService,
    user_id: str,
    session_id: str | None = None,
) -> tuple[VerifiedTriage, ProposedIssue | None, BugTrace]:
    resolve_backend()
    session = None
    if session_id:
        session = await session_service.get_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
    if session is None:
        session = await session_service.create_session(
            app_name=APP_NAME, user_id=user_id, session_id=session_id
        )
    runner = Runner(app_name=APP_NAME, agent=build_pipeline(), session_service=session_service)
    trace = BugTrace(invocation_id=str(uuid.uuid4()))
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            invocation_id=trace.invocation_id,
            new_message=types.Content(
                role="user", parts=[types.Part(text=request.model_dump_json())]
            ),
        ):
            trace.events += 1
            if event.error_code:
                raise PipelineError(f"{event.error_code}: {event.error_message}")
            _collect(event, trace)
    except errors.APIError as exc:
        if exc.code == 429:
            raise ProviderBlocked(QUOTA_GUIDANCE) from exc
        raise
    finally:
        await runner.close()

    final = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session.id
    )
    if final is None:
        raise PipelineError("Session disappeared before the triage could be read")
    verified = final.state.get("verified_triage")
    if verified is None:
        raise PipelineError(
            "The pipeline produced no verified triage. The MCP search most likely "
            "failed; inspect the recorded stages for its reported outcome."
        )
    draft_state = final.state.get("proposed_issue")
    draft = None
    if draft_state is not None:
        try:
            draft = (
                ProposedIssue.model_validate_json(draft_state)
                if isinstance(draft_state, str)
                else ProposedIssue.model_validate(draft_state)
            )
        except ValueError:
            # A malformed draft is dropped; a write cannot be offered without one.
            draft = None
    return VerifiedTriage.model_validate(verified), draft, trace
