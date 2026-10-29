"""The authorized write path, deliberately separate from everything read-only.

Creating an issue is the one irreversible action in Part C, so it is gated four ways:
a separate opt-in setting, a separately scoped token, a separate write-capable MCP
endpoint, and a single-use approval grant that is bound to the exact content the user
was shown. Changing one character of the previewed issue invalidates the grant.

Nothing here can be reached by a model deciding to call it: the grant is minted
server-side from a preview and must be presented back by the user.
"""

import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams

from agents.bug_assistant.config import BugSettings
from agents.bug_assistant.mcp import McpUnavailable, require_allowed
from agents.bug_assistant.models import CreatedIssue, ProposedIssue

GRANT_TTL_SECONDS = 900.0
STATE_KEY = "issue_approval_grant"


class ApprovalRequired(RuntimeError):
    """The write was not authorized, or the authorization does not match the content."""


def content_digest(proposal: ProposedIssue) -> str:
    """Hash the exact fields that would be sent, with stable key ordering."""
    canonical = json.dumps(proposal.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class ApprovalGrant:
    token: str
    content_sha256: str
    repository: str
    subject: str
    issued_at: float
    used: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "content_sha256": self.content_sha256,
            "repository": self.repository,
            "subject": self.subject,
            "issued_at": self.issued_at,
            "used": self.used,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ApprovalGrant":
        return cls(
            token=str(raw["token"]),
            content_sha256=str(raw["content_sha256"]),
            repository=str(raw["repository"]),
            subject=str(raw["subject"]),
            issued_at=float(raw["issued_at"]),
            used=bool(raw.get("used", False)),
        )


def mint_grant(
    proposal: ProposedIssue, subject: str, settings: BugSettings | None = None
) -> ApprovalGrant:
    """Offer an approval for one exact proposal. Minting grants nothing by itself."""
    repository = require_allowed(proposal.owner, proposal.repo, settings)
    return ApprovalGrant(
        token=secrets.token_urlsafe(32),
        content_sha256=content_digest(proposal),
        repository=repository,
        subject=subject,
        issued_at=time.time(),
    )


def authorize(
    grant: ApprovalGrant | None,
    presented_token: str,
    proposal: ProposedIssue,
    subject: str,
    *,
    now: float | None = None,
) -> None:
    """Refuse unless this exact proposal was approved by this user, once, recently."""
    if grant is None:
        raise ApprovalRequired("BLOCKED_NO_APPROVAL: no approval was requested for this session")
    if grant.used:
        raise ApprovalRequired("BLOCKED_APPROVAL_REPLAYED: this approval was already used")
    moment = time.time() if now is None else now
    if moment - grant.issued_at > GRANT_TTL_SECONDS:
        raise ApprovalRequired("BLOCKED_APPROVAL_EXPIRED: request a fresh approval")
    if not secrets.compare_digest(grant.token, presented_token):
        raise ApprovalRequired("BLOCKED_APPROVAL_MISMATCH: the approval token does not match")
    if not secrets.compare_digest(grant.subject, subject):
        raise ApprovalRequired("BLOCKED_APPROVAL_SUBJECT: the approval belongs to another user")
    if not secrets.compare_digest(grant.content_sha256, content_digest(proposal)):
        raise ApprovalRequired(
            "BLOCKED_CONTENT_CHANGED: the issue content differs from what was approved"
        )
    if grant.repository != f"{proposal.owner.lower()}/{proposal.repo.lower()}":
        raise ApprovalRequired("BLOCKED_REPOSITORY_CHANGED: the target repository was altered")


def write_connection(settings: BugSettings | None = None) -> StreamableHTTPConnectionParams:
    config = settings or BugSettings()
    missing = config.write_missing()
    if missing:
        raise ApprovalRequired(
            "BLOCKED_WRITE_DISABLED: the write path is off. To enable it set "
            f"{', '.join(missing)} in agents/bug_assistant/.env, using a second token "
            "scoped to write Issues on one repository."
        )
    url = config.github_write_mcp_url
    if not url.startswith("https://api.githubcopilot.com/mcp/"):
        raise ApprovalRequired(f"GITHUB_WRITE_MCP_URL is not a GitHub MCP endpoint: {url!r}")
    return StreamableHTTPConnectionParams(
        url=url,
        headers={"Authorization": "Bearer " + config.github_write_token.get_secret_value()},
        timeout=60.0,
    )


async def create_issue(
    proposal: ProposedIssue, settings: BugSettings | None = None
) -> CreatedIssue:
    """Perform the write over a separate write-capable MCP connection.

    Callers must have passed `authorize` first; this function does not re-derive
    consent, so it is private to the approved path.
    """
    config = settings or BugSettings()
    require_allowed(proposal.owner, proposal.repo, config)
    toolset = McpToolset(connection_params=write_connection(config))
    try:
        tools = {tool.name: tool for tool in await toolset.get_tools()}
        creator = tools.get("create_issue") or tools.get("issue_write")
        if creator is None:
            raise McpUnavailable(
                "BLOCKED_NO_WRITE_TOOL: the configured endpoint advertises no issue "
                f"creation tool; it offered {sorted(tools)}"
            )
        raw = await creator.run_async(
            args={
                "owner": proposal.owner,
                "repo": proposal.repo,
                "title": proposal.title,
                "body": proposal.body,
            },
            tool_context=None,
        )
    finally:
        await toolset.close()
    return parse_created(raw)


def parse_created(raw: Any) -> CreatedIssue:
    """Read the provider's own identifiers. A write is not claimed without them."""
    text = raw if isinstance(raw, str) else json.dumps(raw, default=str)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise McpUnavailable("The issue creation response was not JSON") from exc
    # MCP wraps tool results in a content envelope; unwrap one level when present.
    if isinstance(payload, dict) and isinstance(payload.get("content"), list):
        for part in payload["content"]:
            if isinstance(part, dict) and part.get("type") == "text":
                try:
                    payload = json.loads(part["text"])
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
                break
    if not isinstance(payload, dict):
        raise McpUnavailable("The issue creation response was not an object")
    number, url = payload.get("number"), payload.get("html_url") or payload.get("url")
    if not isinstance(number, int) or not isinstance(url, str) or not url:
        raise McpUnavailable(
            "The provider returned no issue number and URL, so no issue is claimed created"
        )
    return CreatedIssue(number=number, url=url, state=str(payload.get("state", "unknown")))
