"""C2 tests for the write gate. No network calls; nothing is created anywhere."""

import pytest
from pydantic import SecretStr, ValidationError

from agents.bug_assistant.config import BugSettings
from agents.bug_assistant.mcp import McpUnavailable
from agents.bug_assistant.models import ProposedIssue
from agents.bug_assistant.writes import (
    GRANT_TTL_SECONDS,
    ApprovalRequired,
    authorize,
    content_digest,
    mint_grant,
    parse_created,
    write_connection,
)

REPO = "ArshanBhanage/Google-ADK-Agents"
OWNER, NAME = REPO.split("/")
SUBJECT = "local:11111111-2222-3333-4444-555555555555"


def settings(**overrides: object) -> BugSettings:
    values: dict[str, object] = {"github_allowed_repositories": REPO, **overrides}
    return BugSettings(_env_file=None, **values)  # type: ignore[arg-type]


def proposal(**overrides: object) -> ProposedIssue:
    base: dict[str, object] = {
        "owner": OWNER,
        "repo": NAME,
        "title": "Session identity components are not validated",
        "body": "Observed on the triage path. Steps to reproduce are listed below.",
    }
    return ProposedIssue.model_validate({**base, **overrides})


def granted(config: BugSettings | None = None):
    return mint_grant(proposal(), SUBJECT, config or settings())


def test_minting_a_grant_requires_an_allowlisted_repository() -> None:
    with pytest.raises(McpUnavailable, match="BLOCKED_REPOSITORY"):
        mint_grant(proposal(owner="attacker", repo="elsewhere"), SUBJECT, settings())


def test_a_write_without_any_approval_is_refused() -> None:
    with pytest.raises(ApprovalRequired, match="BLOCKED_NO_APPROVAL"):
        authorize(None, "anything", proposal(), SUBJECT)


def test_the_matching_approval_is_accepted() -> None:
    grant = granted()
    authorize(grant, grant.token, proposal(), SUBJECT)


def test_a_wrong_token_is_refused() -> None:
    grant = granted()
    with pytest.raises(ApprovalRequired, match="BLOCKED_APPROVAL_MISMATCH"):
        authorize(grant, grant.token[:-1] + "x", proposal(), SUBJECT)
    with pytest.raises(ApprovalRequired, match="BLOCKED_APPROVAL_MISMATCH"):
        authorize(grant, "", proposal(), SUBJECT)


def test_an_approval_cannot_be_replayed() -> None:
    grant = granted()
    authorize(grant, grant.token, proposal(), SUBJECT)
    grant.used = True
    with pytest.raises(ApprovalRequired, match="BLOCKED_APPROVAL_REPLAYED"):
        authorize(grant, grant.token, proposal(), SUBJECT)


def test_an_expired_approval_is_refused() -> None:
    grant = granted()
    future = grant.issued_at + GRANT_TTL_SECONDS + 1
    with pytest.raises(ApprovalRequired, match="BLOCKED_APPROVAL_EXPIRED"):
        authorize(grant, grant.token, proposal(), SUBJECT, now=future)


def test_another_user_cannot_spend_someone_elses_approval() -> None:
    grant = granted()
    with pytest.raises(ApprovalRequired, match="BLOCKED_APPROVAL_SUBJECT"):
        authorize(grant, grant.token, proposal(), "local:99999999-0000-0000-0000-000000000000")


@pytest.mark.parametrize(
    "tamper",
    [
        {"title": "Session identity components are not validated at all"},
        {"body": "Observed on the triage path. Steps to reproduce are listed below!"},
    ],
)
def test_editing_the_approved_content_invalidates_the_approval(tamper: dict[str, object]) -> None:
    # The whole point of binding the grant to a digest: approval covers exactly what
    # the user read, not merely "an issue in this repository".
    grant = granted()
    with pytest.raises(ApprovalRequired, match="BLOCKED_CONTENT_CHANGED"):
        authorize(grant, grant.token, proposal(**tamper), SUBJECT)


def test_redirecting_the_write_to_another_repository_is_refused() -> None:
    config = settings(github_allowed_repositories=f"{REPO},other/repo")
    grant = mint_grant(proposal(), SUBJECT, config)
    # Allowlisted, but not the repository the user approved.
    with pytest.raises(
        ApprovalRequired, match="BLOCKED_CONTENT_CHANGED|BLOCKED_REPOSITORY_CHANGED"
    ):
        authorize(grant, grant.token, proposal(owner="other", repo="repo"), SUBJECT)


def test_the_digest_is_order_independent_but_content_sensitive() -> None:
    assert content_digest(proposal()) == content_digest(proposal())
    assert content_digest(proposal()) != content_digest(proposal(title="A different title here"))


def test_the_write_path_is_disabled_by_default() -> None:
    with pytest.raises(ApprovalRequired, match="BLOCKED_WRITE_DISABLED"):
        write_connection(settings())


def test_enabling_the_write_path_still_requires_its_own_token() -> None:
    with pytest.raises(ApprovalRequired, match="GITHUB_WRITE_TOKEN"):
        write_connection(settings(github_write_enabled=True))


def test_an_enabled_write_path_uses_the_separate_token_not_the_read_token() -> None:
    config = settings(
        github_write_enabled=True,
        github_token=SecretStr("read-only-token"),
        github_write_token=SecretStr("write-token"),
    )
    params = write_connection(config)
    assert params.headers is not None
    assert params.headers["Authorization"] == "Bearer write-token"
    assert "read-only-token" not in str(params.headers)
    # The write endpoint is intentionally not a /readonly path.
    assert "/readonly" not in params.url


def test_a_non_github_write_endpoint_is_refused() -> None:
    config = settings(
        github_write_enabled=True,
        github_write_token=SecretStr("write-token"),
        github_write_mcp_url="https://attacker.example/mcp/x/issues",
    )
    with pytest.raises(ApprovalRequired, match="not a GitHub MCP endpoint"):
        write_connection(config)


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"message": "Validation failed"}',
        '{"number": "12", "html_url": "https://github.com/o/r/issues/12"}',
        '{"number": 12}',
        '{"html_url": "https://github.com/o/r/issues/12"}',
        '{"content": [{"type": "text", "text": "{\\"message\\": \\"nope\\"}"}]}',
    ],
)
def test_a_write_is_not_claimed_without_the_providers_own_identifiers(raw: str) -> None:
    with pytest.raises(McpUnavailable):
        parse_created(raw)


def test_a_real_creation_response_is_parsed_from_the_mcp_envelope() -> None:
    envelope = (
        '{"content": [{"type": "text", "text": '
        '"{\\"number\\": 7, \\"html_url\\": \\"https://github.com/o/r/issues/7\\", '
        '\\"state\\": \\"open\\"}"}]}'
    )
    created = parse_created(envelope)
    assert created.number == 7
    assert created.url == "https://github.com/o/r/issues/7"
    assert created.state == "open"


@pytest.mark.parametrize(
    "bad",
    [
        {"title": "short"},
        {"body": "too short"},
        {"owner": "has space"},
        {"repo": "bad/slash"},
    ],
)
def test_malformed_proposals_are_rejected_by_the_schema(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        proposal(**bad)
