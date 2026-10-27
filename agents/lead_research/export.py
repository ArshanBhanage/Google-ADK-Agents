import csv
import io

from agents.lead_research.models import LeadReport

COLUMNS = (
    "name",
    "domain",
    "score",
    "confidence",
    "verification",
    "match_explanation",
    "source_urls",
    "earliest_retrieved_at",
    "content_sha256",
)
# Lead names and excerpts originate from untrusted web pages. A spreadsheet treats a
# leading =, +, - or @ as a formula, so those values are prefixed before writing.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def neutralise(value: str) -> str:
    return "'" + value if value.startswith(FORMULA_PREFIXES) else value


def report_to_csv(report: LeadReport) -> str:
    """Serialise exactly what the report holds. Empty reports produce a header only."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    for lead in report.leads:
        writer.writerow(
            {
                "name": neutralise(lead.name),
                "domain": neutralise(lead.domain),
                "score": lead.score,
                "confidence": lead.confidence,
                "verification": lead.verification,
                "match_explanation": neutralise(lead.match_explanation),
                "source_urls": " ".join(citation.url for citation in lead.citations),
                "earliest_retrieved_at": min(
                    (citation.retrieved_at for citation in lead.citations), default=""
                ),
                "content_sha256": " ".join(citation.content_sha256 for citation in lead.citations),
            }
        )
    return buffer.getvalue()
