"""The authorized path for posting a review comment to GitHub.

Review is read-only by default. Posting is a side effect on someone else's repository,
so it is gated the same way Part C gates issue creation: a separate opt-in, a separately
scoped token, and a single-use approval grant bound to the SHA-256 of the exact comment
body, the repository, the pull request number and the user.

This never approves a pull request and never merges anything. The only verb used is
posting one issue comment on the pull request thread.
"""

import hashlib
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from agents.code_reviewer.config import ReviewSettings
from agents.code_reviewer.github import ReviewUnavailable, require_allowed

GRANT_TTL_SECONDS = 900.0
STATE_KEY = "review_comment_grant"
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class CommentApprovalRequired(RuntimeError):
    """The comment was not authorized, or the authorization does not match it."""


class ProposedComment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner: str = Field(min_length=1, max_length=39, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")
    repo: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    pull_request: int = Field(ge=1, le=10_000_000)
    body: str = Field(min_length=20, max_length=60000)


class PostedComment(BaseModel):
    id: int
    url: str


def comment_digest(proposal: ProposedComment) -> str:
    canonical = json.dumps(proposal.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass
class CommentGrant:
    token: str
    content_sha256: str
    repository: str
    pull_request: int
    subject: str
    issued_at: float
    used: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "content_sha256": self.content_sha256,
            "repository": self.repository,
            "pull_request": self.pull_request,
            "subject": self.subject,
            "issued_at": self.issued_at,
            "used": self.used,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CommentGrant":
        return cls(
            token=str(raw["token"]),
            content_sha256=str(raw["content_sha256"]),
            repository=str(raw["repository"]),
            pull_request=int(raw["pull_request"]),
            subject=str(raw["subject"]),
            issued_at=float(raw["issued_at"]),
            used=bool(raw.get("used", False)),
        )


def mint_grant(
    proposal: ProposedComment, subject: str, settings: ReviewSettings | None = None
) -> CommentGrant:
    repository = require_allowed(proposal.owner, proposal.repo, settings)
    return CommentGrant(
        token=secrets.token_urlsafe(32),
        content_sha256=comment_digest(proposal),
        repository=repository,
        pull_request=proposal.pull_request,
        subject=subject,
        issued_at=time.time(),
    )


def authorize(
    grant: CommentGrant | None,
    presented_token: str,
    proposal: ProposedComment,
    subject: str,
    *,
    now: float | None = None,
) -> None:
    if grant is None:
        raise CommentApprovalRequired(
            "BLOCKED_NO_APPROVAL: no comment approval was requested for this session"
        )
    if grant.used:
        raise CommentApprovalRequired("BLOCKED_APPROVAL_REPLAYED: this approval was already used")
    moment = time.time() if now is None else now
    if moment - grant.issued_at > GRANT_TTL_SECONDS:
        raise CommentApprovalRequired("BLOCKED_APPROVAL_EXPIRED: request a fresh approval")
    if not secrets.compare_digest(grant.token, presented_token):
        raise CommentApprovalRequired(
            "BLOCKED_APPROVAL_MISMATCH: the approval token does not match"
        )
    if not secrets.compare_digest(grant.subject, subject):
        raise CommentApprovalRequired(
            "BLOCKED_APPROVAL_SUBJECT: the approval belongs to another user"
        )
    if not secrets.compare_digest(grant.content_sha256, comment_digest(proposal)):
        raise CommentApprovalRequired(
            "BLOCKED_CONTENT_CHANGED: the comment differs from what was approved"
        )
    if grant.repository != f"{proposal.owner.lower()}/{proposal.repo.lower()}":
        raise CommentApprovalRequired(
            "BLOCKED_REPOSITORY_CHANGED: the target repository was altered"
        )
    if grant.pull_request != proposal.pull_request:
        raise CommentApprovalRequired("BLOCKED_TARGET_CHANGED: the pull request number was altered")


def write_credentials(settings: ReviewSettings | None = None) -> str:
    config = settings or ReviewSettings()
    if not config.review_comment_enabled:
        raise CommentApprovalRequired(
            "BLOCKED_COMMENT_DISABLED: posting review comments is off. To enable it set "
            "REVIEW_COMMENT_ENABLED=true in agents/code_reviewer/.env, with a second "
            "token scoped to write Pull Requests on one repository."
        )
    token = config.review_comment_token.get_secret_value()
    if not token:
        raise CommentApprovalRequired(
            "BLOCKED_COMMENT_TOKEN: set REVIEW_COMMENT_TOKEN in agents/code_reviewer/.env."
        )
    return token


async def post_comment(
    proposal: ProposedComment, settings: ReviewSettings | None = None
) -> PostedComment:
    """Post one comment. Callers must have passed `authorize` first."""
    config = settings or ReviewSettings()
    repository = require_allowed(proposal.owner, proposal.repo, config)
    token = write_credentials(config)
    url = f"{config.github_api_url}/repos/{repository}/issues/{proposal.pull_request}/comments"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(
            url,
            json={"body": proposal.body},
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
    if response.status_code not in {200, 201}:
        raise ReviewUnavailable(
            f"Posting the comment failed with HTTP {response.status_code}; no comment is claimed"
        )
    payload = response.json()
    identifier, link = payload.get("id"), payload.get("html_url")
    if not isinstance(identifier, int) or not isinstance(link, str) or not link:
        raise ReviewUnavailable(
            "GitHub returned no comment id and URL, so no comment is claimed posted"
        )
    return PostedComment(id=identifier, url=link)
