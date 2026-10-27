from collections.abc import AsyncGenerator
from urllib.parse import urlsplit

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types
from pydantic import ValidationError

from agents.lead_research.models import (
    CandidateLead,
    CandidateReport,
    Citation,
    Lead,
    LeadReport,
    SourcePage,
)


def canonical_domain(domain: str) -> str:
    host = urlsplit(domain if "://" in domain else "https://" + domain).hostname
    if not host:
        raise ValueError("Company domain is missing")
    return host.encode("idna").decode("ascii").lower().removeprefix("www.")


def _normalise(text: str) -> str:
    return " ".join(text.split())


def verified_citations(candidate: CandidateLead, evidence: dict[str, SourcePage]) -> list[Citation]:
    """Keep only citations whose excerpt is present in the page we actually fetched.

    The timestamp and digest come from the retrieved page, never from the model.
    """
    citations: list[Citation] = []
    for proposed in candidate.citations:
        page = evidence.get(proposed.url)
        if page is None:
            continue
        body = _normalise(page.text)
        if _normalise(proposed.excerpt) not in body:
            continue
        if candidate.name.casefold() not in page.text.casefold():
            continue
        try:
            citations.append(
                Citation(
                    url=page.url,
                    retrieved_at=page.retrieved_at,
                    excerpt=proposed.excerpt,
                    content_sha256=page.content_sha256,
                )
            )
        except ValidationError:
            # Model-supplied excerpt violated the published contract; drop the citation.
            continue
    return citations


def qualify_report(report: CandidateReport, evidence: dict[str, SourcePage]) -> LeadReport:
    """Turn unverified candidates into a ranked report backed by retrieved bytes."""
    unique: dict[str, Lead] = {}
    discarded = 0
    for candidate in report.leads:
        citations = verified_citations(candidate, evidence)
        if not citations:
            discarded += 1
            continue
        try:
            domain = canonical_domain(candidate.domain)
            hosts = {canonical_domain(citation.url) for citation in citations}
        except (ValueError, UnicodeError):
            # An unparseable domain from untrusted output is dropped, not guessed at.
            discarded += 1
            continue
        from_own_site = domain in hosts
        corroborated = len(hosts) > 1
        try:
            qualified = Lead(
                name=candidate.name,
                domain=domain,
                match_explanation=candidate.match_explanation,
                score=40 + (30 if from_own_site else 0) + (20 if corroborated else 0),
                confidence="high" if from_own_site and corroborated else "medium",
                verification="source_retrieved",
                citations=citations,
            )
        except ValidationError:
            discarded += 1
            continue
        previous = unique.get(domain)
        if previous is None or qualified.score > previous.score:
            unique[domain] = qualified
    return LeadReport(
        leads=sorted(unique.values(), key=lambda item: (-item.score, item.domain)),
        limitations=report.limitations
        + [
            f"Discarded {discarded} candidates without matching retrieved text and company name.",
            "Score measures source completeness, not proven commercial suitability.",
        ],
    )


class EvidenceRanker(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        raw = ctx.session.state.get("candidate_report")
        report = (
            CandidateReport.model_validate_json(raw)
            if isinstance(raw, str)
            else CandidateReport.model_validate(raw)
        )
        evidence = {
            url: SourcePage.model_validate(page)
            for url, page in ctx.session.state.get("source_evidence", {}).items()
        }
        result = qualify_report(report, evidence)
        yield Event(
            author=self.name,
            content=types.Content(role="model", parts=[types.Part(text=result.model_dump_json())]),
            actions=EventActions(state_delta={"lead_report": result.model_dump(mode="json")}),
        )
