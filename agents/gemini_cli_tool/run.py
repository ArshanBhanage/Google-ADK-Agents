import uuid
from dataclasses import dataclass, field
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.genai import errors, types

from agents.gemini_cli_tool.agent import build_pipeline
from agents.gemini_cli_tool.models import CliAnswer, CliPlan, GroundingCheck
from packages.agent_core.provider import resolve_backend

APP_NAME = "gemini_cli_tool"


class PipelineError(RuntimeError):
    """The pipeline produced no verified answer."""


class ProviderBlocked(PipelineError):
    """A provider capability the pipeline depends on is unavailable."""


QUOTA_GUIDANCE = (
    "BLOCKED_PROVIDER_QUOTA: the Gemini API returned 429 RESOURCE_EXHAUSTED after the "
    "configured retries. No answer is substituted. Run `make probe-lead` to see which "
    "capability is exhausted."
)


@dataclass
class Stage:
    """One observable step, labelled with what actually executed it."""

    name: str
    kind: str
    outcome: str
    detail: str = ""


@dataclass
class CliTrace:
    invocation_id: str
    events: int = 0
    stages: list[Stage] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    cli_invocation: dict[str, Any] | None = None
    prompt_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0

    @property
    def cli_actually_ran(self) -> bool:
        record = self.cli_invocation
        return record is not None and record.get("exit_code") == 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "invocation_id": self.invocation_id,
            "events": self.events,
            "cli_actually_ran": self.cli_actually_ran,
            "stages": [vars(stage) for stage in self.stages],
            "tool_calls": self.tool_calls,
            "cli_invocation": self.cli_invocation,
            "usage": {
                "prompt_tokens": self.prompt_tokens,
                "output_tokens": self.output_tokens,
                "thought_tokens": self.thought_tokens,
            },
        }


# Which stage is a model call and which is a subprocess is the distinction Part B has
# to make visible, so it is recorded rather than inferred in the UI.
STAGE_KINDS = {
    "cli_planner": "adk_llm_agent",
    "cli_executor": "adk_llm_agent",
    "cli_grounding": "adk_deterministic_agent",
    "cli_synthesiser": "adk_llm_agent",
}


def _collect(event: Any, trace: CliTrace) -> None:
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
            trace.tool_calls.append(part.function_call.name)
            trace.stages.append(
                Stage(
                    name=part.function_call.name,
                    kind="gemini_cli_subprocess",
                    outcome="called",
                )
            )
        if part.function_response:
            response = part.function_response.response
            status = (
                response.get("status", "returned") if isinstance(response, dict) else "returned"
            )
            trace.stages.append(
                Stage(
                    name=part.function_response.name,
                    kind="gemini_cli_subprocess",
                    outcome=str(status),
                    detail=str(response.get("reason", ""))[:300]
                    if isinstance(response, dict)
                    else "",
                )
            )


async def run_cli_pipeline(
    question: str,
    *,
    session_service: BaseSessionService,
    user_id: str,
    session_id: str | None = None,
) -> tuple[CliAnswer, GroundingCheck, CliPlan | None, CliTrace]:
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
    trace = CliTrace(invocation_id=str(uuid.uuid4()))
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            invocation_id=trace.invocation_id,
            new_message=types.Content(
                role="user", parts=[types.Part(text=f'{{"question": {question!r}}}')]
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
        raise PipelineError("Session disappeared before the answer could be read")
    record = final.state.get("cli_invocation")
    trace.cli_invocation = record if isinstance(record, dict) else None
    verdict = final.state.get("grounding_check")
    answer = final.state.get("cli_final")
    if verdict is None or answer is None:
        raise PipelineError(
            "The pipeline produced no verified answer. The CLI step most likely failed; "
            "inspect the recorded stages for its reported outcome."
        )
    plan_state = final.state.get("cli_plan")
    plan = None
    if plan_state is not None:
        plan = (
            CliPlan.model_validate_json(plan_state)
            if isinstance(plan_state, str)
            else CliPlan.model_validate(plan_state)
        )
    return (
        CliAnswer.model_validate_json(answer)
        if isinstance(answer, str)
        else CliAnswer.model_validate(answer),
        GroundingCheck.model_validate(verdict),
        plan,
        trace,
    )
