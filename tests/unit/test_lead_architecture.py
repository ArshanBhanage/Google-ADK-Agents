import hashlib
import ipaddress
from datetime import UTC, datetime

import pytest
from google.adk.agents import LlmAgent
from pydantic import ValidationError

from agents.lead_research.agent import root_agent
from agents.lead_research.models import Citation, Lead, LeadReport, ResearchRequest, SourcePage
from agents.lead_research.ranking import canonical_domain, qualify_report
from agents.lead_research.sources import SourceError, VisibleText, require_public, validate_url


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:password@example.com",  # pragma: allowlist secret -- rejection input
        "https://localhost",
        "https://metadata.google.internal",
        "https://example.com:8080",
        "https://example.com/#x",
        "https://example.com/\r\nHeader: x",
        "https://example.com\\@localhost",
    ],
)
def test_unsafe_urls_rejected(url: str) -> None:
    with pytest.raises((ValueError, SourceError)):
        validate_url(url)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fc00::1"])
def test_private_dns_answer_rejected(address: str) -> None:
    with pytest.raises(SourceError):
        require_public([address])
    assert not ipaddress.ip_address(address).is_global


def test_mixed_dns_answers_fail_closed() -> None:
    with pytest.raises(SourceError):
        require_public(["8.8.8.8", "127.0.0.1"])
    with pytest.raises(SourceError):
        require_public([])


def test_plain_text_extraction_excludes_scripts() -> None:
    parser = VisibleText()
    parser.feed("<title>Title</title><script>hidden()</script><p>Visible &amp; text</p>")
    assert parser.title == ["Title"]
    assert parser.parts == ["Title", "Visible & text"]


def test_criteria_requires_complete_bounded_request() -> None:
    with pytest.raises(ValidationError):
        ResearchRequest(
            industry="software", region="US", buyer_profile="small teams", quantity=1000
        )
    with pytest.raises(ValidationError):
        ResearchRequest.model_validate({"industry": "software"})
    parsed = ResearchRequest(
        industry="software", region="US", buyer_profile="small engineering teams", quantity=3
    )
    assert parsed.quantity == 3


def test_root_agent_contains_real_specialist_pipeline() -> None:
    assert root_agent.name == "lead_research"
    pipeline = root_agent.tools[0].agent
    assert [agent.name for agent in pipeline.sub_agents] == [
        "market_research",
        "candidate_discovery",
        "source_validator",
        "evidence_ranker",
    ]
    assert len(pipeline.sub_agents[1].sub_agents) == 2
    # Qualification must not be delegated to a model: the ranker is a plain BaseAgent.
    assert not isinstance(pipeline.sub_agents[3], LlmAgent)


def _page(url: str, text: str) -> SourcePage:
    body = text.encode()
    return SourcePage(
        url=url,
        retrieved_at=datetime(2026, 10, 26, 12, 0, tzinfo=UTC),
        title="Example",
        text=text,
        content_sha256=hashlib.sha256(body).hexdigest(),
    )


def _claim(name: str, domain: str, cited: list[tuple[str, str]]) -> Lead:
    """An unverified model claim: digests are placeholders until evidence is matched."""
    return Lead(
        name=name,
        domain=domain,
        match_explanation="model claim pending verification",
        confidence="low",
        verification="unverified",
        citations=[
            Citation(
                url=url,
                retrieved_at=datetime(2026, 10, 26, 12, 0, tzinfo=UTC),
                excerpt=excerpt,
                content_sha256="0" * 64,
            )
            for url, excerpt in cited
        ],
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("WWW.Example.COM", "example.com"),
        ("https://www.Example.com/path", "example.com"),
        ("münchen.de", "xn--mnchen-3ya.de"),
    ],
)
def test_domain_normalisation(raw: str, expected: str) -> None:
    assert canonical_domain(raw) == expected


def test_unsupported_claims_are_discarded_not_downgraded() -> None:
    text = "Northwind Logistics operates three depots."
    evidence = {"https://northwind.example/about": _page("https://northwind.example/about", text)}
    url = "https://northwind.example/about"
    report = LeadReport(
        leads=[
            # Excerpt is absent from the retrieved page.
            _claim("Northwind Logistics", "northwind.example", [(url, "invented quote")]),
            # Excerpt matches, but the page never names this company.
            _claim("Unrelated Corp", "unrelated.example", [(url, "three depots")]),
            # No citation at all.
            _claim("Phantom Ltd", "phantom.example", []),
        ],
        limitations=[],
    )
    qualified = qualify_report(report, evidence)
    assert qualified.leads == []
    assert any("Discarded 3 candidates" in line for line in qualified.limitations)


def test_verified_leads_are_deduplicated_and_ranked_by_evidence() -> None:
    own = "Northwind Logistics operates three depots in Ohio."
    third_party = "Northwind Logistics expanded its Ohio depots this year."
    evidence = {
        "https://northwind.example/about": _page("https://northwind.example/about", own),
        "https://trade-press.example/news": _page("https://trade-press.example/news", third_party),
    }
    both = _claim(
        "Northwind Logistics",
        "www.northwind.example",
        [
            ("https://northwind.example/about", "three depots in Ohio"),
            ("https://trade-press.example/news", "expanded its Ohio depots"),
        ],
    )
    third_party_only = _claim(
        "Northwind Logistics",
        "northwind.example",
        [("https://trade-press.example/news", "expanded its Ohio depots")],
    )
    qualified = qualify_report(LeadReport(leads=[third_party_only, both], limitations=[]), evidence)
    # Both claims normalise to one organisation; the better-evidenced one survives.
    assert len(qualified.leads) == 1
    lead = qualified.leads[0]
    assert lead.domain == "northwind.example"
    assert lead.verification == "source_retrieved"
    assert lead.confidence == "high"
    assert lead.score == 90
    assert {citation.content_sha256 for citation in lead.citations} == {
        evidence[url].content_sha256 for url in evidence
    }


def test_citation_digest_is_replaced_by_the_retrieved_bytes() -> None:
    text = "Acme Tooling sells CNC fixtures."
    evidence = {"https://acme.example/": _page("https://acme.example/", text)}
    claimed = _claim(
        "Acme Tooling", "acme.example", [("https://acme.example/", "sells CNC fixtures")]
    )
    assert claimed.citations[0].content_sha256 == "0" * 64
    qualified = qualify_report(LeadReport(leads=[claimed], limitations=[]), evidence)
    assert (
        qualified.leads[0].citations[0].content_sha256
        == evidence["https://acme.example/"].content_sha256
    )
    # One third-party-free citation set scores lower than corroborated evidence.
    assert qualified.leads[0].score == 70
