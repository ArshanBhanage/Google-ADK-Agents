import os

from google.adk.agents import Agent, ParallelAgent, SequentialAgent
from google.adk.agents.context import Context
from google.adk.models.google_llm import Gemini
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.google_search_tool import google_search
from google.genai import types

from agents.lead_research import prompts
from agents.lead_research.models import LeadReport, ResearchRequest
from agents.lead_research.ranking import EvidenceRanker
from agents.lead_research.tools import inspect_public_source
from packages.agent_core.config import Settings

DEFAULT_MODEL = "gemini-3.8-flash"
# Free-tier keys rate-limit per minute; grounded discovery runs two searches at once.
RETRY = types.HttpRetryOptions(
    attempts=6,
    initial_delay=5.0,
    exp_base=2.0,
    max_delay=90.0,
    jitter=1.0,
    http_status_codes=[429, 500, 502, 503, 504],
)


def ensure_provider() -> None:
    """Fail closed before any billable call; export the key only into this process."""
    settings = Settings()
    missing = [
        name
        for name, value in (
            ("GOOGLE_API_KEY", settings.google_api_key.get_secret_value()),
            ("GEMINI_MODEL", settings.gemini_model),
        )
        if not value
    ]
    if missing:
        raise ValueError("BLOCKED: set " + ", ".join(missing) + " in the local root .env")
    os.environ["GOOGLE_API_KEY"] = settings.google_api_key.get_secret_value()


def require_provider(callback_context: Context) -> None:
    ensure_provider()


def build_model() -> Gemini:
    """One model per agent instance so retry state is not shared across stages."""
    return Gemini(model=Settings().gemini_model or DEFAULT_MODEL, retry_options=RETRY)


def build_pipeline() -> SequentialAgent:
    """The execution stages that run after the user has confirmed criteria."""
    common = types.GenerateContentConfig(temperature=0.2, max_output_tokens=4096)
    market = Agent(
        name="market_research",
        model=build_model(),
        instruction=prompts.MARKET,
        tools=[google_search],
        output_key="market_brief",
        generate_content_config=common,
    )
    primary = Agent(
        name="primary_discovery",
        model=build_model(),
        instruction=prompts.DISCOVERY.replace("{focus}", "direct company sites and product pages"),
        tools=[google_search],
        output_key="primary_candidates",
        generate_content_config=common,
    )
    secondary = Agent(
        name="secondary_discovery",
        model=build_model(),
        instruction=prompts.DISCOVERY.replace(
            "{focus}", "public industry sources and expansion news"
        ),
        tools=[google_search],
        output_key="secondary_candidates",
        generate_content_config=common,
    )
    validator = Agent(
        name="source_validator",
        model=build_model(),
        instruction=prompts.VALIDATE,
        tools=[inspect_public_source],
        output_key="candidate_report",
        output_schema=LeadReport,
        generate_content_config=common,
    )
    return SequentialAgent(
        name="research_pipeline",
        input_schema=ResearchRequest,
        description="Research an explicitly confirmed ideal customer profile.",
        sub_agents=[
            market,
            ParallelAgent(name="candidate_discovery", sub_agents=[primary, secondary]),
            validator,
            EvidenceRanker(name="evidence_ranker"),
        ],
    )


def build_agent() -> Agent:
    return Agent(
        name="lead_research",
        model=build_model(),
        instruction=prompts.INTAKE,
        tools=[AgentTool(agent=build_pipeline(), propagate_grounding_metadata=True)],
        before_agent_callback=require_provider,
        generate_content_config=types.GenerateContentConfig(
            temperature=0.2, max_output_tokens=4096
        ),
    )


root_agent = build_agent()
