"""Live A1 gate. Requires real Gemini credentials; never passes without them."""

import pytest
from google.adk.sessions import InMemorySessionService

from agents.lead_research.models import LeadReport, ResearchRequest
from agents.lead_research.run import ProviderBlocked, ResearchTrace, run_research
from packages.agent_core.config import Settings

pytestmark = pytest.mark.live

REQUEST = ResearchRequest(
    industry="industrial CNC machining services",
    region="Ohio, United States",
    buyer_profile="independent machine shops publishing their own capability pages",
    quantity=3,
)


@pytest.fixture(scope="module")
def settings() -> Settings:
    config = Settings()
    missing = [
        name
        for name, value in (
            ("GOOGLE_API_KEY", config.google_api_key.get_secret_value()),
            ("GEMINI_MODEL", config.gemini_model),
        )
        if not value
    ]
    if missing:
        pytest.skip(f"SKIPPED (credentials missing): {', '.join(missing)}")
    return config


@pytest.fixture(scope="module")
async def outcome(settings: Settings) -> tuple[LeadReport, ResearchTrace]:
    try:
        return await run_research(
            REQUEST, session_service=InMemorySessionService(), user_id="live-gate"
        )
    except ProviderBlocked as exc:
        # A quota block is a blocked gate, not a skip and never a pass.
        pytest.fail(str(exc), pytrace=False)


async def test_pipeline_actually_called_google_search(
    outcome: tuple[LeadReport, ResearchTrace],
) -> None:
    _, trace = outcome
    assert trace.used_google_search, "No grounding metadata: search was never executed"
    assert trace.model_versions, "No model version reported by the provider"


async def test_every_returned_lead_is_backed_by_retrieved_bytes(
    outcome: tuple[LeadReport, ResearchTrace],
) -> None:
    report, trace = outcome
    for lead in report.leads:
        assert lead.verification == "source_retrieved"
        assert lead.citations, f"{lead.domain} survived ranking without a citation"
        for citation in lead.citations:
            assert citation.url in trace.retrieved_sources

    # An empty result is an acceptable honest outcome, but it must be explained.
    assert report.limitations


async def test_report_is_deduplicated_and_ordered(
    outcome: tuple[LeadReport, ResearchTrace],
) -> None:
    report, _ = outcome
    domains = [lead.domain for lead in report.leads]
    assert len(domains) == len(set(domains))
    assert [lead.score for lead in report.leads] == sorted(
        (lead.score for lead in report.leads), reverse=True
    )
