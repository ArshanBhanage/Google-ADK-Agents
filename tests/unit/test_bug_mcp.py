"""C1 tests: MCP scope and repository allowlist enforcement. No network calls."""

import pytest
from pydantic import SecretStr

from agents.bug_assistant.mcp import (
    READ_ONLY_TOOLS,
    WRITE_MARKERS,
    McpUnavailable,
    admissible,
    allowed_repositories,
    connection,
    require_allowed,
    validate_url,
)
from packages.agent_core.config import Settings


def settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


class FakeTool:
    """A stand-in for an advertised MCP tool. Only `name` is consulted."""

    def __init__(self, name: str) -> None:
        self.name = name


READONLY_URL = "https://api.githubcopilot.com/mcp/x/issues/readonly"


@pytest.mark.parametrize(
    "url",
    [
        "https://api.githubcopilot.com/mcp/",
        "https://api.githubcopilot.com/mcp/x/issues",
        "https://api.githubcopilot.com/mcp/x/all",
    ],
)
def test_a_write_capable_url_is_refused(url: str) -> None:
    with pytest.raises(McpUnavailable, match="BLOCKED_WRITE_CAPABLE_URL"):
        validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.githubcopilot.com/mcp/x/issues/readonly",
        "https://evil.example/mcp/x/issues/readonly",
        "https://api.githubcopilot.com.evil.example/mcp/readonly",
        "ftp://api.githubcopilot.com/mcp/readonly",
    ],
)
def test_untrusted_or_plaintext_endpoints_are_refused(url: str) -> None:
    with pytest.raises(McpUnavailable, match="must be HTTPS"):
        validate_url(url)


def test_the_documented_readonly_url_is_accepted() -> None:
    assert validate_url(READONLY_URL) == READONLY_URL
    assert validate_url("https://api.githubcopilot.com/mcp/readonly/insiders")


def test_a_missing_token_fails_closed() -> None:
    with pytest.raises(McpUnavailable, match="BLOCKED_GITHUB_TOKEN"):
        connection(settings(github_mcp_url=READONLY_URL))


def test_the_connection_sends_the_readonly_header_and_bearer_token() -> None:
    params = connection(
        settings(github_mcp_url=READONLY_URL, github_token=SecretStr("t0ken-value"))
    )
    assert params.url == READONLY_URL
    assert params.headers is not None
    assert params.headers["X-MCP-Readonly"] == "true"
    assert params.headers["Authorization"] == "Bearer t0ken-value"


def test_an_empty_allowlist_blocks_every_repository() -> None:
    with pytest.raises(McpUnavailable, match="BLOCKED_GITHUB_ALLOWLIST"):
        require_allowed("google", "adk-python", settings())


@pytest.mark.parametrize("entry", ["justowner", "owner/repo/extra", "/repo", "owner/"])
def test_malformed_allowlist_entries_are_refused(entry: str) -> None:
    with pytest.raises(McpUnavailable, match="owner/repo form"):
        allowed_repositories(settings(github_allowed_repositories=entry))


def test_only_allowlisted_repositories_are_admitted() -> None:
    config = settings(github_allowed_repositories="google/adk-python, Owner/Other")
    assert require_allowed("google", "adk-python", config) == "google/adk-python"
    # Case and surrounding whitespace must not be a way past the allowlist.
    assert require_allowed("  OWNER ", " OTHER ", config) == "owner/other"
    for owner, repo in (("google", "evil-repo"), ("attacker", "adk-python")):
        with pytest.raises(McpUnavailable, match="BLOCKED_REPOSITORY"):
            require_allowed(owner, repo, config)


def test_a_write_tool_on_a_readonly_endpoint_is_refused_outright() -> None:
    # Defence in depth: if the server ever widens what it advertises, this stops it
    # rather than silently granting the agent a mutation it was never authorized.
    advertised = [FakeTool("search_issues"), FakeTool("create_issue")]
    with pytest.raises(McpUnavailable, match="BLOCKED_WRITE_TOOL_ADVERTISED"):
        admissible(advertised)  # type: ignore[arg-type]


@pytest.mark.parametrize("marker", sorted(WRITE_MARKERS))
def test_every_write_marker_is_actually_rejected(marker: str) -> None:
    with pytest.raises(McpUnavailable):
        admissible([FakeTool(f"issue_{marker}_thing")])  # type: ignore[arg-type]


def test_unknown_read_tools_are_dropped_rather_than_trusted() -> None:
    advertised = [FakeTool("search_issues"), FakeTool("some_unvetted_read_tool")]
    assert [tool.name for tool in admissible(advertised)] == ["search_issues"]  # type: ignore[arg-type]


def test_the_allowlist_matches_the_tools_observed_on_the_readonly_endpoint() -> None:
    # Recorded from a real handshake; see docs/evidence/c1-mcp-gate.txt.
    observed = {
        "get_label",
        "issue_read",
        "list_issue_fields",
        "list_issue_types",
        "list_issues",
        "search_issues",
    }
    assert READ_ONLY_TOOLS == observed
