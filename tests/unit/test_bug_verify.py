"""C2 tests for deterministic duplicate verification. No network calls."""

from typing import Any

from agents.bug_assistant.models import DuplicateCandidate, TriageReport
from agents.bug_assistant.verify import verify_triage

REAL = {
    "7800": {
        "number": 7800,
        "title": "FirestoreSessionService does not validate identity components",
        "url": "https://github.com/google/adk-python/issues/7800",
        "state": "open",
        "updated_at": "2026-10-29T04:12:40Z",
    }
}


def claim(number: int, **overrides: Any) -> DuplicateCandidate:
    base: dict[str, Any] = {
        "number": number,
        "title": "whatever the model remembered",
        "url": "https://example.invalid/not-real",
        "state": "closed",
        "updated_at": "1999-01-01T00:00:00Z",
        "why_similar": "same symptom",
    }
    return DuplicateCandidate.model_validate({**base, **overrides})


def report(*claims: DuplicateCandidate, limitations: list[str] | None = None) -> TriageReport:
    return TriageReport(
        severity="high",
        severity_rationale="cross-identity data exposure",
        root_cause_hypothesis="unvalidated path segments",
        reproduction_steps=["create a session with a slash in user_id"],
        debugging_checklist=["log the resolved document path"],
        duplicate_candidates=list(claims),
        next_action="validate identity components",
        limitations=limitations or [],
    )


def test_identity_fields_come_from_the_provider_not_the_model() -> None:
    # The model's title, url, state and timestamp are all wrong here on purpose.
    verified = verify_triage(report(claim(7800)), REAL, "google/adk-python")
    (duplicate,) = verified.verified_duplicates
    assert duplicate.url == REAL["7800"]["url"]
    assert duplicate.title == REAL["7800"]["title"]
    assert duplicate.state == "open"
    assert duplicate.updated_at == "2026-10-29T04:12:40Z"
    # Only the reasoning is kept from the model.
    assert duplicate.why_similar == "same symptom"


def test_an_issue_that_was_never_retrieved_is_discarded() -> None:
    verified = verify_triage(report(claim(999999)), REAL, "google/adk-python")
    assert verified.verified_duplicates == []
    assert verified.discarded_duplicates == ["#999999 was not in the retrieved issues"]
    assert any("discarded as unsupported" in line for line in verified.report.limitations)


def test_discarded_claims_do_not_survive_into_the_report() -> None:
    verified = verify_triage(report(claim(7800), claim(123)), REAL, "google/adk-python")
    numbers = [item.number for item in verified.report.duplicate_candidates]
    assert numbers == [7800]


def test_the_same_issue_claimed_twice_appears_once() -> None:
    verified = verify_triage(report(claim(7800), claim(7800)), REAL, "google/adk-python")
    assert len(verified.verified_duplicates) == 1


def test_the_hypothesis_caveat_always_reaches_the_user() -> None:
    # Regression: these limitations were computed and then dropped, so the report
    # presented a hypothesis without ever labelling it unconfirmed.
    verified = verify_triage(report(claim(7800)), REAL, "google/adk-python")
    assert any("hypothesis" in line for line in verified.report.limitations)


def test_no_retrieved_issues_is_stated_rather_than_implied_clean() -> None:
    verified = verify_triage(report(), {}, "owner/repo")
    assert verified.issues_searched == 0
    assert any("No issues were retrieved" in line for line in verified.report.limitations)


def test_searching_without_finding_a_duplicate_is_distinguished_from_not_searching() -> None:
    verified = verify_triage(report(), REAL, "google/adk-python")
    assert verified.issues_searched == 1
    assert any("none matched closely enough" in line for line in verified.report.limitations)
    assert not any("No issues were retrieved" in line for line in verified.report.limitations)


def test_pre_existing_limitations_are_preserved() -> None:
    verified = verify_triage(
        report(claim(7800), limitations=["could not inspect runtime logs"]),
        REAL,
        "google/adk-python",
    )
    assert "could not inspect runtime logs" in verified.report.limitations
