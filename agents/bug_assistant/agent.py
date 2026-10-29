"""ADK pipeline: triage over real MCP issue data, verified deterministically.

`issue_triage` is an LlmAgent whose only tool reaches the MCP server. `issue_verifier`
is a plain BaseAgent that runs no model and decides which duplicate claims survive.
`issue_drafter` writes a proposal that files nothing; the write path is a separate,
separately authorized route in `writes.py`.
"""

from collections.abc import AsyncGenerator

from google.adk.agents import Agent, BaseAgent, SequentialAgent
from google.adk.agents.context import Context
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.models.google_llm import Gemini
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

from agents.bug_assistant import prompts
from agents.bug_assistant.models import BugTriageRequest, ProposedIssue, TriageReport
from agents.bug_assistant.tools import search_repository_issues
from agents.bug_assistant.verify import verify_triage
from agents.lead_research.agent import DEFAULT_MODEL, RETRY
from packages.agent_core.config import Settings
from packages.agent_core.provider import resolve_backend


def require_provider(callback_context: Context) -> None:
    resolve_backend()


def build_model() -> Gemini:
    return Gemini(model=Settings().gemini_model or DEFAULT_MODEL, retry_options=RETRY)


class IssueVerifier(BaseAgent):
    """Discards duplicate claims the retrieved issues do not support. Runs no model."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        raw = ctx.session.state.get("triage_report")
        evidence = ctx.session.state.get("issue_evidence") or {}
        repository = str(ctx.session.state.get("issue_repository", ""))
        report = (
            TriageReport.model_validate_json(raw)
            if isinstance(raw, str)
            else TriageReport.model_validate(raw)
        )
        verified = verify_triage(report, evidence, repository)
        yield Event(
            author=self.name,
            content=types.Content(
                role="model", parts=[types.Part(text=verified.model_dump_json())]
            ),
            actions=EventActions(state_delta={"verified_triage": verified.model_dump(mode="json")}),
        )


def build_pipeline() -> SequentialAgent:
    common = types.GenerateContentConfig(temperature=0.1, max_output_tokens=4096)
    triage = Agent(
        name="issue_triage",
        model=build_model(),
        instruction=prompts.TRIAGE,
        tools=[search_repository_issues],
        output_key="triage_report",
        output_schema=TriageReport,
        generate_content_config=common,
    )
    drafter = Agent(
        name="issue_drafter",
        model=build_model(),
        instruction=prompts.PROPOSE,
        output_key="proposed_issue",
        output_schema=ProposedIssue,
        generate_content_config=common,
    )
    return SequentialAgent(
        name="bug_pipeline",
        input_schema=BugTriageRequest,
        description="Triage a reported bug against real issues in an allowlisted repository.",
        sub_agents=[triage, IssueVerifier(name="issue_verifier"), drafter],
    )


def build_agent() -> Agent:
    return Agent(
        name="bug_assistant",
        model=build_model(),
        instruction=prompts.SAFETY
        + """
Collect the repository owner, repository name and a bug description, then call
bug_pipeline once. Report the severity and its rationale, the verified duplicate issues
with their real numbers and URLs, the reproduction steps, the debugging checklist and
every limitation. Present the drafted issue as a draft only: you cannot file it, and
filing requires the user to approve the exact content through the application.
""",
        tools=[AgentTool(agent=build_pipeline())],
        before_agent_callback=require_provider,
        generate_content_config=types.GenerateContentConfig(
            temperature=0.1, max_output_tokens=4096
        ),
    )


root_agent = build_agent()
