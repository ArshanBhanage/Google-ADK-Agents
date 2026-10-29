"""Deterministic check of the triage report against the issues actually retrieved.

A duplicate claim is the one part of this report that points at a real, citable object,
so it is the part a model must not be trusted to assert. Any claimed duplicate whose
number is absent from the retrieved evidence is discarded, and the ones that survive
have their title, URL, state and timestamp overwritten with the recorded values.
"""

from typing import Any

from agents.bug_assistant.models import DuplicateCandidate, TriageReport, VerifiedTriage


def verify_triage(
    report: TriageReport, evidence: dict[str, Any], repository: str
) -> VerifiedTriage:
    verified: list[DuplicateCandidate] = []
    discarded: list[str] = []
    seen: set[int] = set()

    for claim in report.duplicate_candidates:
        record = evidence.get(str(claim.number))
        if not isinstance(record, dict):
            discarded.append(f"#{claim.number} was not in the retrieved issues")
            continue
        if claim.number in seen:
            continue
        seen.add(claim.number)
        verified.append(
            DuplicateCandidate(
                number=claim.number,
                # Identity fields come from the provider, not the model.
                title=str(record.get("title", "")),
                url=str(record.get("url", "")),
                state=str(record.get("state", "")),
                updated_at=str(record.get("updated_at", "")),
                why_similar=claim.why_similar,
            )
        )

    limitations = list(report.limitations)
    if discarded:
        limitations.append(
            f"{len(discarded)} duplicate claim(s) were discarded as unsupported: "
            + "; ".join(discarded[:5])
        )
    if not evidence:
        limitations.append(
            "No issues were retrieved, so no duplicate could be confirmed or ruled out."
        )
    elif not verified:
        limitations.append(
            f"{len(evidence)} issue(s) were searched and none matched closely enough to "
            "be called a duplicate."
        )
    limitations.append(
        "The root cause is a hypothesis from the description and issue text, not a "
        "diagnosis confirmed by running the code."
    )
    return VerifiedTriage(
        report=report.model_copy(
            update={"duplicate_candidates": verified, "limitations": limitations}
        ),
        verified_duplicates=verified,
        discarded_duplicates=discarded,
        repository=repository,
        issues_searched=len(evidence),
    )
