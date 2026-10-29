"""Real MCP connection to the official remote GitHub MCP server.

Transport is Streamable HTTP to `https://api.githubcopilot.com/mcp/...`, which is the
documented remote endpoint. Nothing here calls the GitHub REST API directly and then
calls itself MCP: tools are whatever the server advertises over the protocol.

Scope is enforced three times over, because one layer is not a boundary:

1. The URL must be a `/readonly` toolset path, checked before connecting.
2. `X-MCP-Readonly: true` is sent as well, which is the header equivalent.
3. The tools the server returns are filtered against READ_ONLY_TOOLS, so a server
   change that starts advertising a write tool cannot silently widen this agent.

Observed with 0.65-era server on 2026-10-28: the issues read-only toolset advertises
exactly get_label, issue_read, list_issue_fields, list_issue_types, list_issues and
search_issues. No create, update, comment or label-write tool is present.
"""

from urllib.parse import urlsplit

from google.adk.tools.base_tool import BaseTool
from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams

from packages.agent_core.config import Settings

READ_ONLY_TOOLS = frozenset(
    {
        "search_issues",
        "list_issues",
        "issue_read",
        "get_label",
        "list_issue_fields",
        "list_issue_types",
    }
)
# Any tool name matching these is refused even if it appears on a read-only URL.
WRITE_MARKERS = ("create", "update", "delete", "add", "remove", "comment", "assign", "close")
ALLOWED_HOSTS = frozenset({"api.githubcopilot.com"})
TIMEOUT_SECONDS = 60.0


class McpUnavailable(RuntimeError):
    """The MCP server cannot be reached, or is not configured safely."""


def allowed_repositories(settings: Settings | None = None) -> frozenset[str]:
    """The explicit `owner/repo` allowlist. Untrusted input is matched against this."""
    config = settings or Settings()
    entries = {
        entry.strip().lower()
        for entry in config.github_allowed_repositories.split(",")
        if entry.strip()
    }
    for entry in entries:
        if entry.count("/") != 1 or not all(part for part in entry.split("/")):
            raise McpUnavailable(
                f"GITHUB_ALLOWED_REPOSITORIES entry {entry!r} is not in owner/repo form"
            )
    return frozenset(entries)


def require_allowed(owner: str, repo: str, settings: Settings | None = None) -> str:
    """Resolve a repository only if the operator allowlisted it.

    The owner and repo may originate from a model or from tool output, so neither is
    trusted; this is the single place a target repository is admitted.
    """
    allowlist = allowed_repositories(settings)
    if not allowlist:
        raise McpUnavailable(
            "BLOCKED_GITHUB_ALLOWLIST: set GITHUB_ALLOWED_REPOSITORIES in the local root "
            ".env to a comma-separated list of owner/repo you authorize."
        )
    target = f"{owner.strip().lower()}/{repo.strip().lower()}"
    if target not in allowlist:
        raise McpUnavailable(f"BLOCKED_REPOSITORY: {target} is not in GITHUB_ALLOWED_REPOSITORIES.")
    return target


def validate_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise McpUnavailable(
            f"GITHUB_MCP_URL must be HTTPS on one of {sorted(ALLOWED_HOSTS)}; got {url!r}"
        )
    if "/readonly" not in parsed.path:
        raise McpUnavailable(
            "BLOCKED_WRITE_CAPABLE_URL: GITHUB_MCP_URL must be a /readonly toolset path. "
            "Write access is a separate, separately authorized gate."
        )
    return url


def connection(settings: Settings | None = None) -> StreamableHTTPConnectionParams:
    config = settings or Settings()
    token = config.github_token.get_secret_value()
    if not token:
        raise McpUnavailable(
            "BLOCKED_GITHUB_TOKEN: set GITHUB_TOKEN in the local root .env to a "
            "fine-grained token with read-only Issues access to the allowlisted "
            "repositories. Never paste it into a chat."
        )
    return StreamableHTTPConnectionParams(
        url=validate_url(config.github_mcp_url),
        headers={
            "Authorization": "Bearer " + token,
            # Belt and braces with the /readonly path above.
            "X-MCP-Readonly": "true",
        },
        timeout=TIMEOUT_SECONDS,
    )


def build_toolset(settings: Settings | None = None) -> McpToolset:
    return McpToolset(connection_params=connection(settings))


def admissible(tools: list[BaseTool]) -> list[BaseTool]:
    """Keep only allowlisted read tools, and refuse outright if a write tool appears."""
    offending = [
        tool.name for tool in tools if any(marker in tool.name.lower() for marker in WRITE_MARKERS)
    ]
    if offending:
        raise McpUnavailable(
            "BLOCKED_WRITE_TOOL_ADVERTISED: the MCP server offered write-capable tools "
            f"on a read-only endpoint: {', '.join(sorted(offending))}. Refusing to proceed."
        )
    return [tool for tool in tools if tool.name in READ_ONLY_TOOLS]
