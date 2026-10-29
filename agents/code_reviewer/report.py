"""Deterministic assembly of the review report.

Three jobs, none of which a model may do for itself:

1. Discard any comment that names a file or line the pull request did not change.
2. Deduplicate, including against the tool findings, so a reviewer cannot restate a
   Ruff diagnostic as an independent discovery.
3. Split comments into verified and unverified. A comment matching a diagnostic that
   actually ran is verified and carries its rule code; everything else is the
   reviewer's reading and is labelled as such.
"""

from agents.code_reviewer.analysis import AnalysisResult
from agents.code_reviewer.diff import FileDiff
from agents.code_reviewer.github import PullRequest
from agents.code_reviewer.models import (
    ReviewComment,
    ReviewDraft,
    ReviewReport,
    ToolEvidence,
)

# Within this many lines, a reviewer comment and a tool diagnostic on the same file are
# treated as the same issue. Diagnostics often land a line off from the construct a
# human would point at.
MATCH_WINDOW = 2
STYLE_RULES = ("E1", "E2", "E3", "E5", "W", "I0", "UP", "SIM", "RET", "C4", "PTH")


def is_stylistic(rule: str) -> bool:
    return rule.startswith(STYLE_RULES)


def admissible_lines(files: list[FileDiff]) -> dict[str, FileDiff]:
    return {file.path: file for file in files}


def assemble(
    pull: PullRequest,
    analysis: AnalysisResult,
    draft: ReviewDraft,
    test_status: str,
    test_reason: str,
    test_isolation: dict[str, str],
) -> ReviewReport:
    by_path = admissible_lines(pull.changed_files)
    evidence = [
        ToolEvidence(
            path=finding.path,
            line=finding.line,
            rule=finding.rule,
            message=finding.message,
            source=finding.source,
            severity=finding.severity,
        )
        for finding in analysis.diff_findings
    ]

    verified: list[ReviewComment] = []
    unverified: list[ReviewComment] = []
    discarded: list[str] = []
    seen: set[tuple[str, int, str]] = set()

    for comment in draft.comments:
        file = by_path.get(comment.path)
        if file is None:
            discarded.append(f"{comment.path}:{comment.line} — the diff does not touch this file")
            continue
        if not file.in_diff(comment.line):
            discarded.append(
                f"{comment.path}:{comment.line} — outside the changed lines of this pull request"
            )
            continue
        key = (comment.path, comment.line, comment.category)
        if key in seen:
            discarded.append(f"{comment.path}:{comment.line} — duplicate of an earlier comment")
            continue
        seen.add(key)

        match = next(
            (
                item
                for item in evidence
                if item.path == comment.path and abs(item.line - comment.line) <= MATCH_WINDOW
            ),
            None,
        )
        if match is not None:
            verified.append(comment.model_copy(update={"rule": match.rule}))
        else:
            unverified.append(comment)

    limitations = list(draft.limitations)
    if discarded:
        limitations.append(
            f"{len(discarded)} reviewer comment(s) were discarded for naming a file or "
            "line this pull request did not change."
        )
    if unverified:
        limitations.append(
            f"{len(unverified)} comment(s) are the reviewer's reading of the diff and are "
            "not backed by a tool diagnostic; treat them as unverified."
        )
    if analysis.unanalysed:
        limitations.append(
            f"{len(analysis.unanalysed)} changed file(s) had no configured analyser, so "
            "only the reviewer's reading applies to them."
        )
    if test_status != "passed":
        # The reason already carries its own status prefix when the sandbox set one.
        detail = test_reason.removeprefix(f"{test_status}:").strip() or "no reason recorded"
        limitations.append(
            f"Test execution status is {test_status} ({detail}). No behavioural claim is "
            "made about this change."
        )
    limitations.extend(analysis.notes)
    limitations.extend(pull.truncated)

    return ReviewReport(
        repository=pull.repository,
        pull_request=pull.number,
        title=pull.title,
        head_sha=pull.head_sha,
        url=pull.url,
        summary=draft.summary,
        # A blocking verdict requires something verified or a critical reading, so a
        # model cannot block a change on style alone.
        blocking=draft.blocking
        and bool(
            [c for c in verified if c.severity in {"critical", "high"}]
            or [c for c in unverified if c.severity == "critical"]
        ),
        verified_comments=verified,
        unverified_comments=unverified,
        discarded_comments=discarded,
        tool_evidence=evidence,
        evidence_outside_diff=len(analysis.findings) - len(analysis.diff_findings),
        files_analysed=analysis.analysed_paths,
        files_unanalysed=analysis.unanalysed,
        tool_versions=analysis.tool_versions,
        test_status=test_status,
        test_reason=test_reason,
        test_isolation=test_isolation,
        limitations=limitations,
    )


def to_markdown(report: ReviewReport) -> str:
    """The human-readable rendering. Generated from the same object the UI consumes."""
    lines = [
        f"# Review of {report.repository}#{report.pull_request}",
        "",
        f"**{report.title}**",
        "",
        f"- Commit: `{report.head_sha}`",
        f"- Verdict: {'changes requested' if report.blocking else 'no blocking findings'}",
        f"- Tests: `{report.test_status}`"
        + (f" — {report.test_reason}" if report.test_reason else ""),
        f"- Tools: {', '.join(f'{k} {v}' for k, v in sorted(report.tool_versions.items()))}",
        "",
        "## Summary",
        "",
        report.summary,
    ]
    for heading, comments, note in (
        ("Verified findings", report.verified_comments, "backed by a tool diagnostic"),
        (
            "Unverified findings",
            report.unverified_comments,
            "the reviewer's reading, not tool-confirmed",
        ),
    ):
        if not comments:
            continue
        lines += ["", f"## {heading} ({note})", ""]
        for comment in comments:
            rule = f" `{comment.rule}`" if comment.rule else ""
            where = f"`{comment.path}:{comment.line}`"
            lines += [
                f"### {where} — {comment.severity}/{comment.category}{rule}",
                "",
                comment.finding,
                "",
                f"*Recommendation ({comment.confidence} confidence):* {comment.recommendation}",
                "",
            ]
    if report.limitations:
        lines += ["", "## Limitations", ""]
        lines += [f"- {item}" for item in report.limitations]
    return "\n".join(lines) + "\n"
