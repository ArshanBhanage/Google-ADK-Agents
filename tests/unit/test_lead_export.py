import csv
import io
from datetime import UTC, datetime

from agents.lead_research.export import COLUMNS, report_to_csv
from agents.lead_research.models import Citation, Lead, LeadReport


def _lead(name: str, domain: str, urls: list[str]) -> Lead:
    return Lead(
        name=name,
        domain=domain,
        match_explanation="publishes an equipment list",
        score=70,
        confidence="medium",
        verification="source_retrieved",
        citations=[
            Citation(
                url=url,
                retrieved_at=datetime(2026, 10, 27, 6 + index, 0, tzinfo=UTC),
                excerpt="operates three depots",
                content_sha256=f"{index:064d}",
            )
            for index, url in enumerate(urls)
        ],
    )


def _rows(report: LeadReport) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(report_to_csv(report))))


def test_empty_report_exports_a_header_only() -> None:
    body = report_to_csv(LeadReport(leads=[], limitations=["nothing verified"]))
    assert body.splitlines() == [",".join(COLUMNS)]


def test_export_matches_the_report_values() -> None:
    report = LeadReport(
        leads=[_lead("Wagner Machine", "wagnermachine.com", ["https://wagnermachine.com/a"])],
        limitations=[],
    )
    (row,) = _rows(report)
    lead = report.leads[0]
    assert row["name"] == lead.name
    assert row["domain"] == lead.domain
    assert int(row["score"]) == lead.score
    assert row["confidence"] == lead.confidence
    assert row["verification"] == lead.verification
    assert row["source_urls"] == lead.citations[0].url
    assert row["content_sha256"] == lead.citations[0].content_sha256


def test_multiple_citations_are_listed_with_the_earliest_timestamp() -> None:
    report = LeadReport(
        leads=[
            _lead("Acme", "acme.example", ["https://acme.example/a", "https://trade.example/b"])
        ],
        limitations=[],
    )
    (row,) = _rows(report)
    assert row["source_urls"].split() == ["https://acme.example/a", "https://trade.example/b"]
    assert row["earliest_retrieved_at"].startswith("2026-10-27 06:00")


def test_spreadsheet_formula_injection_is_neutralised() -> None:
    # A company name is scraped from an untrusted page and must not become a formula.
    hostile = '=HYPERLINK("https://attacker.example","clickme")'
    report = LeadReport(
        leads=[_lead(hostile, "acme.example", ["https://acme.example/"])], limitations=[]
    )
    (row,) = _rows(report)
    assert row["name"].startswith("'=")
    assert not row["name"].startswith("=")


def test_quoting_keeps_separators_inside_one_field() -> None:
    report = LeadReport(
        leads=[_lead('Smith, Jones "and" Co', "smith.example", ["https://smith.example/"])],
        limitations=[],
    )
    (row,) = _rows(report)
    assert row["name"] == 'Smith, Jones "and" Co'
    assert len(_rows(report)) == 1
