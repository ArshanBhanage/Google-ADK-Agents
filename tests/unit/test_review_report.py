"""D2 tests: report assembly, dedup, verdict discipline and the comment gate."""

import pytest
from pydantic import SecretStr, ValidationError

from agents.code_reviewer.analysis import AnalysisResult, Finding
from agents.code_reviewer.comments import (
    GRANT_TTL_SECONDS,
    CommentApprovalRequired,
    ProposedComment,
    authorize,
    comment_digest,
    mint_grant,
    write_credentials,
)
from agents.code_reviewer.config import ReviewSettings
from agents.code_reviewer.diff import FileDiff
from agents.code_reviewer.github import PullRequest
from agents.code_reviewer.models import ReviewComment, ReviewDraft
from agents.code_reviewer.report import assemble, is_stylistic, to_markdown

REPO = "google/adk-python"
OWNER, NAME = REPO.split("/")
SUBJECT = "local:1111"


def settings(**overrides: object) -> ReviewSettings:
    values: dict[str, object] = {"github_allowed_repositories": REPO, **overrides}
    return ReviewSettings(_env_file=None, **values)  # type: ignore[arg-type]


def pull() -> PullRequest:
    return PullRequest(
        repository=REPO,
        number=7801,
        title="fix: validate identity components",
        state="open",
        head_sha="e" * 40,
        base_sha="b" * 40,
        author="someone",
        url=f"https://github.com/{REPO}/pull/7801",
        changed_files=[
            FileDiff(
                path="src/mod.py",
                status="modified",
                additions=4,
                deletions=1,
                hunk_ranges=[(10, 20)],
            ),
            FileDiff(
                path="README.md", status="modified", additions=1, deletions=0, hunk_ranges=[(1, 3)]
            ),
        ],
        truncated=[],
    )


def analysis(*findings: Finding) -> AnalysisResult:
    return AnalysisResult(
        findings=list(findings),
        analysed_paths=["src/mod.py"],
        unanalysed=[],
        tool_versions={"ruff": "0.17.2"},
        notes=[],
    )


def finding(line: int, rule: str = "F821", severity: str = "high") -> Finding:
    return Finding(
        path="src/mod.py",
        line=line,
        rule=rule,
        message="undefined name",
        source="ruff",
        severity=severity,
        in_diff=True,
    )


def comment(path: str, line: int, **overrides: object) -> ReviewComment:
    base: dict[str, object] = {
        "path": path,
        "line": line,
        "severity": "high",
        "category": "correctness",
        "finding": "this breaks",
        "recommendation": "fix it",
        "confidence": "high",
    }
    return ReviewComment.model_validate({**base, **overrides})


def draft(*comments: ReviewComment, blocking: bool = False) -> ReviewDraft:
    return ReviewDraft(
        summary="A change.", comments=list(comments), blocking=blocking, limitations=[]
    )


def build(d: ReviewDraft, a: AnalysisResult | None = None, status: str = "tests_not_run"):
    return assemble(pull(), a or analysis(), d, status, f"{status}: by policy", {})


def test_a_comment_on_an_untouched_file_is_discarded() -> None:
    report = build(draft(comment("src/other.py", 12)))
    assert report.verified_comments == []
    assert report.unverified_comments == []
    assert "does not touch this file" in report.discarded_comments[0]


def test_a_comment_outside_the_changed_lines_is_discarded() -> None:
    report = build(draft(comment("src/mod.py", 99)))
    assert "outside the changed lines" in report.discarded_comments[0]


def test_a_comment_inside_the_changed_lines_survives() -> None:
    report = build(draft(comment("src/mod.py", 15)))
    assert len(report.unverified_comments) == 1


def test_a_comment_matching_a_diagnostic_is_verified_and_carries_its_rule() -> None:
    report = build(draft(comment("src/mod.py", 15)), analysis(finding(15)))
    (verified,) = report.verified_comments
    assert verified.rule == "F821"
    assert report.unverified_comments == []


def test_a_diagnostic_a_line_or_two_away_still_counts_as_the_same_issue() -> None:
    report = build(draft(comment("src/mod.py", 15)), analysis(finding(17)))
    assert len(report.verified_comments) == 1


def test_a_distant_diagnostic_does_not_verify_a_comment() -> None:
    report = build(draft(comment("src/mod.py", 11)), analysis(finding(19)))
    assert report.verified_comments == []
    assert len(report.unverified_comments) == 1


def test_unverified_comments_are_labelled_in_the_limitations() -> None:
    report = build(draft(comment("src/mod.py", 15)))
    assert any("not backed by a tool diagnostic" in line for line in report.limitations)


def test_two_comments_on_the_same_line_and_category_are_deduplicated() -> None:
    report = build(draft(comment("src/mod.py", 15), comment("src/mod.py", 15)))
    assert len(report.unverified_comments) == 1
    assert any("duplicate" in line for line in report.discarded_comments)


def test_the_same_line_in_a_different_category_is_not_a_duplicate() -> None:
    report = build(draft(comment("src/mod.py", 15), comment("src/mod.py", 15, category="security")))
    assert len(report.unverified_comments) == 2


def test_style_alone_cannot_block_a_change() -> None:
    # A model asking to block on a preference is overruled by the assembler.
    report = build(
        draft(comment("src/mod.py", 15, severity="low", category="style"), blocking=True)
    )
    assert report.blocking is False


def test_a_verified_high_severity_finding_can_block() -> None:
    report = build(draft(comment("src/mod.py", 15), blocking=True), analysis(finding(15)))
    assert report.blocking is True


def test_a_critical_reading_can_block_without_a_diagnostic() -> None:
    report = build(draft(comment("src/mod.py", 15, severity="critical"), blocking=True))
    assert report.blocking is True


def test_a_non_blocking_draft_is_never_escalated() -> None:
    report = build(draft(comment("src/mod.py", 15), blocking=False), analysis(finding(15)))
    assert report.blocking is False


def test_an_unexecuted_suite_is_stated_in_the_limitations() -> None:
    report = build(draft(), status="tests_not_run")
    assert any("No behavioural claim" in line for line in report.limitations)
    # The status prefix is not repeated inside its own explanation.
    assert not any("tests_not_run: tests_not_run" in line for line in report.limitations)


@pytest.mark.parametrize("rule", ["E501", "UP045", "SIM117", "I001", "RET504"])
def test_style_rules_are_recognised(rule: str) -> None:
    assert is_stylistic(rule) is True


@pytest.mark.parametrize("rule", ["F821", "S608", "B008", "ASYNC101"])
def test_substantive_rules_are_not_stylistic(rule: str) -> None:
    assert is_stylistic(rule) is False


def test_the_markdown_renders_from_the_same_object_the_ui_consumes() -> None:
    report = build(draft(comment("src/mod.py", 15)), analysis(finding(15)))
    text = to_markdown(report)
    assert "google/adk-python#7801" in text
    assert "src/mod.py:15" in text
    assert "no blocking findings" in text
    assert "ruff 0.17.2" in text
    assert "## Limitations" in text


# --- the comment-posting gate ---------------------------------------------------------


def proposal(**overrides: object) -> ProposedComment:
    base: dict[str, object] = {
        "owner": OWNER,
        "repo": NAME,
        "pull_request": 7801,
        "body": "Automated review summary with enough characters to be valid.",
    }
    return ProposedComment.model_validate({**base, **overrides})


def test_posting_requires_an_allowlisted_repository() -> None:
    from agents.code_reviewer.github import ReviewUnavailable

    with pytest.raises(ReviewUnavailable, match="BLOCKED_REPOSITORY"):
        mint_grant(proposal(owner="attacker", repo="elsewhere"), SUBJECT, settings())


def test_posting_without_approval_is_refused() -> None:
    with pytest.raises(CommentApprovalRequired, match="BLOCKED_NO_APPROVAL"):
        authorize(None, "token", proposal(), SUBJECT)


def test_a_matching_approval_is_accepted() -> None:
    grant = mint_grant(proposal(), SUBJECT, settings())
    authorize(grant, grant.token, proposal(), SUBJECT)


@pytest.mark.parametrize(
    ("tamper", "expected"),
    [
        ({"body": "A different comment body, long enough to validate."}, "BLOCKED_CONTENT_CHANGED"),
        ({"pull_request": 7802}, "BLOCKED_CONTENT_CHANGED|BLOCKED_TARGET_CHANGED"),
    ],
)
def test_editing_the_approved_comment_invalidates_the_approval(
    tamper: dict[str, object], expected: str
) -> None:
    grant = mint_grant(proposal(), SUBJECT, settings())
    with pytest.raises(CommentApprovalRequired, match=expected):
        authorize(grant, grant.token, proposal(**tamper), SUBJECT)


def test_an_approval_cannot_be_replayed_or_outlive_its_window() -> None:
    grant = mint_grant(proposal(), SUBJECT, settings())
    with pytest.raises(CommentApprovalRequired, match="BLOCKED_APPROVAL_EXPIRED"):
        authorize(
            grant, grant.token, proposal(), SUBJECT, now=grant.issued_at + GRANT_TTL_SECONDS + 1
        )
    grant.used = True
    with pytest.raises(CommentApprovalRequired, match="BLOCKED_APPROVAL_REPLAYED"):
        authorize(grant, grant.token, proposal(), SUBJECT)


def test_another_user_cannot_spend_the_approval() -> None:
    grant = mint_grant(proposal(), SUBJECT, settings())
    with pytest.raises(CommentApprovalRequired, match="BLOCKED_APPROVAL_SUBJECT"):
        authorize(grant, grant.token, proposal(), "local:9999")


def test_commenting_is_disabled_by_default() -> None:
    with pytest.raises(CommentApprovalRequired, match="BLOCKED_COMMENT_DISABLED"):
        write_credentials(settings())


def test_enabling_commenting_still_requires_its_own_token() -> None:
    with pytest.raises(CommentApprovalRequired, match="BLOCKED_COMMENT_TOKEN"):
        write_credentials(settings(review_comment_enabled=True))


def test_the_comment_token_is_separate_from_the_read_token() -> None:
    config = settings(
        review_comment_enabled=True,
        github_token=SecretStr("read-token"),
        review_comment_token=SecretStr("comment-token"),
    )
    assert write_credentials(config) == "comment-token"


def test_the_digest_is_stable_and_content_sensitive() -> None:
    assert comment_digest(proposal()) == comment_digest(proposal())
    assert comment_digest(proposal()) != comment_digest(
        proposal(body="Another body entirely, still long enough.")
    )


@pytest.mark.parametrize(
    "bad",
    [{"body": "too short"}, {"owner": "has space"}, {"pull_request": 0}, {"repo": "bad/slash"}],
)
def test_malformed_comment_proposals_are_refused(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        proposal(**bad)
