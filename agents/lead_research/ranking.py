from collections.abc import AsyncGenerator
from urllib.parse import urlsplit

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from agents.lead_research.models import Citation, Lead, LeadReport, SourcePage


def canonical_domain(domain: str) -> str:
    host = urlsplit(domain if "://" in domain else "https://" + domain).hostname
    if not host:
        raise ValueError("Company domain is missing")
    return host.encode("idna").decode("ascii").lower().removeprefix("www.")


def qualify_report(report: LeadReport, evidence: dict[str, SourcePage]) -> LeadReport:
    unique: dict[str, Lead] = {}
    discarded = 0
    for lead in report.leads:
        citations = []
        for citation in lead.citations:
            page = evidence.get(citation.url)
            excerpt = " ".join(citation.excerpt.split())
            if (
                page
                and excerpt in " ".join(page.text.split())
                and lead.name.casefold() in page.text.casefold()
            ):
                citations.append(
                    Citation(
                        url=page.url,
                        retrieved_at=page.retrieved_at,
                        excerpt=citation.excerpt,
                        content_sha256=page.content_sha256,
                    )
                )
        if not citations:
            discarded += 1
            continue
        domain = canonical_domain(lead.domain)
        hosts = {canonical_domain(c.url) for c in citations}
        direct = domain in hosts
        score = 40 + (30 if direct else 0) + (20 if len(hosts) > 1 else 0)
        qualified = lead.model_copy(
            update={
                "domain": domain,
                "citations": citations,
                "verification": "source_retrieved",
                "score": score,
                "confidence": "high" if direct and len(hosts) > 1 else "medium",
            }
        )
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
            LeadReport.model_validate_json(raw)
            if isinstance(raw, str)
            else LeadReport.model_validate(raw)
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
