import uuid
from dataclasses import dataclass, field
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.genai import errors, types

from agents.lead_research.agent import build_pipeline, ensure_provider
from agents.lead_research.models import LeadReport, ResearchRequest, SourcePage

APP_NAME = "lead_research"


class PipelineError(RuntimeError):
    """The pipeline produced no validated report."""


class ProviderBlocked(PipelineError):
    """A provider capability the pipeline depends on is unavailable for these credentials."""


QUOTA_GUIDANCE = (
    "BLOCKED_PROVIDER_QUOTA: the Gemini API returned 429 RESOURCE_EXHAUSTED after the "
    "configured retries. Lead discovery depends on live Google Search grounding and will "
    "not be substituted with stored or generated results. Run `make probe-lead` to see "
    "which capability is exhausted, then enable paid-tier billing for this key's project "
    "or configure another authorized search API."
)


@dataclass
class ToolInvocation:
    agent: str
    tool: str
    outcome: str


@dataclass
class ResearchTrace:
    """Observable evidence of the run. Holds no credentials and no model reasoning."""

    invocation_id: str
    events: int = 0
    search_queries: list[str] = field(default_factory=list)
    grounding_sources: list[str] = field(default_factory=list)
    tool_invocations: list[ToolInvocation] = field(default_factory=list)
    retrieved_sources: list[str] = field(default_factory=list)
    model_versions: list[str] = field(default_factory=list)
    prompt_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0

    @property
    def used_google_search(self) -> bool:
        return bool(self.search_queries or self.grounding_sources)

    @property
    def billable_searches(self) -> int:
        """Search queries are billed individually, so the count is the cost driver."""
        return len(self.search_queries)

    def as_dict(self) -> dict[str, Any]:
        return {
            "invocation_id": self.invocation_id,
            "events": self.events,
            "used_google_search": self.used_google_search,
            "search_queries": self.search_queries,
            "grounding_sources": self.grounding_sources,
            "model_versions": self.model_versions,
            "tool_invocations": [vars(call) for call in self.tool_invocations],
            "retrieved_sources": self.retrieved_sources,
            "usage": {
                "prompt_tokens": self.prompt_tokens,
                "output_tokens": self.output_tokens,
                "thought_tokens": self.thought_tokens,
                "billable_searches": self.billable_searches,
            },
        }


def _collect(event: Any, trace: ResearchTrace) -> None:
    if event.model_version and event.model_version not in trace.model_versions:
        trace.model_versions.append(event.model_version)
    usage = event.usage_metadata
    if usage:
        trace.prompt_tokens += usage.prompt_token_count or 0
        trace.output_tokens += usage.candidates_token_count or 0
        trace.thought_tokens += usage.thoughts_token_count or 0
    metadata = event.grounding_metadata
    if metadata:
        for query in metadata.web_search_queries or []:
            if query not in trace.search_queries:
                trace.search_queries.append(query)
        for chunk in metadata.grounding_chunks or []:
            uri = getattr(getattr(chunk, "web", None), "uri", None)
            if uri and uri not in trace.grounding_sources:
                trace.grounding_sources.append(uri)
    for part in event.content.parts if event.content and event.content.parts else []:
        if part.function_call:
            trace.tool_invocations.append(
                ToolInvocation(agent=event.author, tool=part.function_call.name, outcome="called")
            )
        if part.function_response:
            response = part.function_response.response
            outcome = "returned"
            if isinstance(response, dict):
                # Only the tool's own status field is recorded; page text is never logged.
                outcome = str(response.get("status", outcome))
            trace.tool_invocations.append(
                ToolInvocation(
                    agent=event.author, tool=part.function_response.name, outcome=outcome
                )
            )


async def run_research(
    request: ResearchRequest,
    *,
    session_service: BaseSessionService,
    user_id: str,
    session_id: str | None = None,
) -> tuple[LeadReport, ResearchTrace]:
    """Execute the confirmed-criteria pipeline and return its deterministic report."""
    ensure_provider()
    session = await session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    runner = Runner(app_name=APP_NAME, agent=build_pipeline(), session_service=session_service)
    trace = ResearchTrace(invocation_id=str(uuid.uuid4()))
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
        raise PipelineError("Session disappeared before the report could be read")
    trace.retrieved_sources = [
        SourcePage.model_validate(page).url
        for page in final.state.get("source_evidence", {}).values()
    ]
    raw = final.state.get("lead_report")
    if raw is None:
        raise PipelineError("The ranking stage produced no lead_report state")
    return LeadReport.model_validate(raw), trace
