"""ADK pipeline: plan in ADK, execute in the real Gemini CLI, verify deterministically.

The three stages are deliberately different in kind, which is the point of Part B.
`cli_planner` is an LlmAgent with no tools. `cli_executor` is an LlmAgent whose only
tool shells out to the pinned `gemini` executable. `cli_grounding` is a plain
BaseAgent that runs no model at all.
"""

from collections.abc import AsyncGenerator
from pathlib import Path

from google.adk.agents import Agent, BaseAgent, SequentialAgent
from google.adk.agents.context import Context
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.models.google_llm import Gemini
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

from agents.gemini_cli_tool import prompts
from agents.gemini_cli_tool.grounding import check_grounding
from agents.gemini_cli_tool.models import CliAnswer, CliPlan, CliRequest
from agents.gemini_cli_tool.tools import inspect_workspace_with_gemini_cli
from agents.lead_research.agent import DEFAULT_MODEL, RETRY
from packages.agent_core.config import Settings
from packages.agent_core.provider import resolve_backend

EXECUTE = (
    prompts.SAFETY
    + """
You are the ADK execution step. Call inspect_workspace_with_gemini_cli exactly once,
passing the planned task unchanged as the `task` argument. Do not answer from your own
knowledge and do not reword the plan. If the tool reports FAILED or BLOCKED, report
that outcome verbatim and stop. Plan: {cli_plan}
"""
)


def require_provider(callback_context: Context) -> None:
    resolve_backend()


def build_model() -> Gemini:
    return Gemini(model=Settings().gemini_model or DEFAULT_MODEL, retry_options=RETRY)


class CliGroundingVerifier(BaseAgent):
    """Checks the CLI answer against the real workspace. Runs no model."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        invocation = ctx.session.state.get("cli_invocation")
        workspace = ctx.session.state.get("cli_workspace")
        if not isinstance(invocation, dict) or not workspace:
            verdict = check_grounding("", Path("/nonexistent"))
            verdict.limitations.insert(0, "The Gemini CLI produced no invocation record.")
        else:
            verdict = check_grounding(str(invocation.get("response", "")), Path(workspace))
        yield Event(
            author=self.name,
            content=types.Content(role="model", parts=[types.Part(text=verdict.model_dump_json())]),
            actions=EventActions(state_delta={"grounding_check": verdict.model_dump(mode="json")}),
        )


def build_pipeline() -> SequentialAgent:
    common = types.GenerateContentConfig(temperature=0.1, max_output_tokens=4096)
    planner = Agent(
        name="cli_planner",
        model=build_model(),
        instruction=prompts.PLAN,
        output_key="cli_plan",
        output_schema=CliPlan,
        generate_content_config=common,
    )
    executor = Agent(
        name="cli_executor",
        model=build_model(),
        instruction=EXECUTE,
        tools=[inspect_workspace_with_gemini_cli],
        output_key="cli_answer",
        generate_content_config=common,
    )
    synthesiser = Agent(
        name="cli_synthesiser",
        model=build_model(),
        instruction=prompts.SYNTHESISE,
        output_key="cli_final",
        output_schema=CliAnswer,
        generate_content_config=common,
    )
    return SequentialAgent(
        name="cli_pipeline",
        input_schema=CliRequest,
        description="Plan in ADK, inspect with the real Gemini CLI, then verify.",
        sub_agents=[
            planner,
            executor,
            CliGroundingVerifier(name="cli_grounding"),
            synthesiser,
        ],
    )


def build_agent() -> Agent:
    return Agent(
        name="gemini_cli_tool",
        model=build_model(),
        instruction=prompts.SAFETY
        + """
Ask for the user's question about the authorized read-only workspace if it is missing,
then call cli_pipeline once with it. Report its answer, the verified paths and every
limitation. Never claim the workspace contains something the pipeline did not verify.
""",
        tools=[AgentTool(agent=build_pipeline())],
        before_agent_callback=require_provider,
        generate_content_config=types.GenerateContentConfig(
            temperature=0.1, max_output_tokens=4096
        ),
    )


root_agent = build_agent()
