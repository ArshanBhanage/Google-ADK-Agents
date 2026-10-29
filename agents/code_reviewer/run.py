import uuid
from dataclasses import dataclass, field
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.genai import errors, types

from agents.code_reviewer.agent import build_pipeline
from agents.code_reviewer.models import ReviewReport, ReviewRequest
from packages.agent_core.provider import resolve_backend

APP_NAME = "code_reviewer"


class PipelineError(RuntimeError):
    """The pipeline produced no review report."""


class ProviderBlocked(PipelineError):
    """A provider capability the pipeline depends on is unavailable."""


QUOTA_GUIDANCE = (
    "BLOCKED_PROVIDER_QUOTA: the Gemini API returned 429 RESOURCE_EXHAUSTED after the "
    "configured retries. No review is substituted."
)

STAGE_KINDS = {
    "review_analysis": "adk_deterministic_agent",
    "review_reasoner": "adk_llm_agent",
    "review_assembler": "adk_deterministic_agent",
}


@dataclass
class Stage:
    name: str
    kind: str
    outcome: str


@dataclass
class ReviewTrace:
    invocation_id: str
    events: int = 0
    stages: list[Stage] = field(default_factory=list)
    prompt_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "invocation_id": self.invocation_id,
            "events": self.events,
            "stages": [vars(stage) for stage in self.stages],
            "usage": {
                "prompt_tokens": self.prompt_tokens,
                "output_tokens": self.output_tokens,
                "thought_tokens": self.thought_tokens,
            },
        }


def _collect(event: Any, trace: ReviewTrace) -> None:
    usage = event.usage_metadata
    if usage:
        trace.prompt_tokens += usage.prompt_token_count or 0
        trace.output_tokens += usage.candidates_token_count or 0
        trace.thought_tokens += usage.thoughts_token_count or 0
    kind = STAGE_KINDS.get(event.author)
    if kind and not any(stage.name == event.author for stage in trace.stages):
        trace.stages.append(Stage(name=event.author, kind=kind, outcome="ran"))


async def run_review(
    request: ReviewRequest,
    *,
    session_service: BaseSessionService,
    user_id: str,
    session_id: str | None = None,
) -> tuple[ReviewReport, ReviewTrace]:
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
    trace = ReviewTrace(invocation_id=str(uuid.uuid4()))
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            invocation_id=trace.invocation_id,
            new_message=types.Content(
                role="user", parts=[types.Part(text=request.model_dump_json())]
            ),
            state_delta={"review_request": request.model_dump(mode="json")},
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
        raise PipelineError("Session disappeared before the report could be read")
    report = final.state.get("review_report")
    if report is None:
        raise PipelineError(
            "The pipeline produced no review report. Retrieval or analysis most likely "
            "failed; inspect the recorded stages."
        )
    return ReviewReport.model_validate(report), trace
