"""Authenticated, read-only pull request retrieval.

Part C connects through MCP because that is what Part C is about. Part D uses GitHub's
REST API directly, which the deliverable contract asks for here, with only read verbs:
nothing in this module issues a POST, PATCH, PUT or DELETE.
"""

import base64
from dataclasses import dataclass
from typing import Any

import httpx

from agents.code_reviewer.config import ReviewSettings
from agents.code_reviewer.diff import FileDiff, build_file_diff, safe_path

TIMEOUT = httpx.Timeout(30.0, connect=10.0)
MAX_FILE_BYTES = 400_000


class ReviewUnavailable(RuntimeError):
    """The pull request cannot be retrieved, or is not authorized for review."""


@dataclass
class PullRequest:
    repository: str
    number: int
    title: str
    state: str
    head_sha: str
    base_sha: str
    author: str
    url: str
    changed_files: list[FileDiff]
    truncated: list[str]

    @property
    def python_files(self) -> list[FileDiff]:
        return [
            file
            for file in self.changed_files
            if file.language == "python" and file.status != "removed"
        ]


def allowed_repositories(settings: ReviewSettings | None = None) -> frozenset[str]:
    config = settings or ReviewSettings()
    entries = {
        entry.strip().lower()
        for entry in config.github_allowed_repositories.split(",")
        if entry.strip()
    }
    for entry in entries:
        if entry.count("/") != 1 or not all(part for part in entry.split("/")):
            raise ReviewUnavailable(
                f"GITHUB_ALLOWED_REPOSITORIES entry {entry!r} is not in owner/repo form"
            )
    return frozenset(entries)


def require_allowed(owner: str, repo: str, settings: ReviewSettings | None = None) -> str:
    allowlist = allowed_repositories(settings)
    if not allowlist:
        raise ReviewUnavailable(
            "BLOCKED_REVIEW_ALLOWLIST: set GITHUB_ALLOWED_REPOSITORIES in "
            "agents/code_reviewer/.env to the repositories you authorize for review."
        )
    target = f"{owner.strip().lower()}/{repo.strip().lower()}"
    if target not in allowlist:
        raise ReviewUnavailable(f"BLOCKED_REPOSITORY: {target} is not authorized for review.")
    return target


def headers(settings: ReviewSettings) -> dict[str, str]:
    token = settings.github_token.get_secret_value()
    if not token:
        raise ReviewUnavailable(
            "BLOCKED_GITHUB_TOKEN: set GITHUB_TOKEN in agents/code_reviewer/.env to a "
            "fine-grained token with read access to Pull Requests and Contents."
        )
    return {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _raise_for(response: httpx.Response, what: str) -> None:
    if response.status_code == 404:
        raise ReviewUnavailable(f"{what} was not found, or the token cannot see it")
    if response.status_code in {401, 403}:
        remaining = response.headers.get("x-ratelimit-remaining")
        if remaining == "0":
            raise ReviewUnavailable(
                "BLOCKED_RATE_LIMIT: the GitHub API rate limit is exhausted; "
                f"it resets at {response.headers.get('x-ratelimit-reset', 'unknown')}"
            )
        raise ReviewUnavailable(f"{what} was refused ({response.status_code}); check token scopes")
    if response.status_code >= 400:
        raise ReviewUnavailable(f"{what} failed with HTTP {response.status_code}")


async def fetch_pull_request(
    owner: str, repo: str, number: int, settings: ReviewSettings | None = None
) -> PullRequest:
    config = settings or ReviewSettings()
    repository = require_allowed(owner, repo, config)
    if number <= 0:
        raise ReviewUnavailable("A pull request number must be positive")
    base = f"{config.github_api_url}/repos/{repository}/pulls/{number}"
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers(config)) as client:
        meta = await client.get(base)
        _raise_for(meta, f"Pull request {repository}#{number}")
        payload: dict[str, Any] = meta.json()

        files: list[dict[str, Any]] = []
        for page in range(1, 6):
            listing = await client.get(f"{base}/files", params={"per_page": 100, "page": page})
            _raise_for(listing, f"Files for {repository}#{number}")
            batch = listing.json()
            if not isinstance(batch, list) or not batch:
                break
            files.extend(item for item in batch if isinstance(item, dict))
            if len(batch) < 100:
                break

    truncated: list[str] = []
    if len(files) > config.max_changed_files:
        truncated.append(
            f"The pull request changes {len(files)} files; only the first "
            f"{config.max_changed_files} were retrieved for analysis."
        )
        files = files[: config.max_changed_files]

    diffs: list[FileDiff] = []
    budget = config.max_patch_bytes
    for entry in files:
        diff = build_file_diff(entry)
        if not safe_path(diff.path):
            truncated.append(f"Skipped an unsafe path in the diff: {diff.path!r}")
            continue
        patch = entry.get("patch")
        if isinstance(patch, str):
            budget -= len(patch)
            if budget < 0:
                truncated.append(
                    f"Patch budget exhausted; {diff.path} and later files were not parsed."
                )
                break
        elif diff.status != "removed":
            truncated.append(
                f"{diff.path} has no patch (binary or above GitHub's size limit), so no "
                "line-level finding can be attributed to it."
            )
        diffs.append(diff)

    head = payload.get("head") or {}
    basebranch = payload.get("base") or {}
    return PullRequest(
        repository=repository,
        number=number,
        title=str(payload.get("title", "")),
        state=str(payload.get("state", "")),
        head_sha=str(head.get("sha", "")) if isinstance(head, dict) else "",
        base_sha=str(basebranch.get("sha", "")) if isinstance(basebranch, dict) else "",
        author=str((payload.get("user") or {}).get("login", "")),
        url=str(payload.get("html_url", "")),
        changed_files=diffs,
        truncated=truncated,
    )


async def fetch_file(
    repository: str, path: str, ref: str, settings: ReviewSettings | None = None
) -> str | None:
    """Fetch one file's text at a commit. Returns None when it is not readable text."""
    config = settings or ReviewSettings()
    if not safe_path(path):
        return None
    url = f"{config.github_api_url}/repos/{repository}/contents/{path}"
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=headers(config)) as client:
        response = await client.get(url, params={"ref": ref})
    if response.status_code == 404:
        return None
    _raise_for(response, f"Contents of {path}")
    payload = response.json()
    if not isinstance(payload, dict) or payload.get("encoding") != "base64":
        return None
    try:
        raw = base64.b64decode(payload.get("content", ""), validate=False)
    except (ValueError, TypeError):
        return None
    if len(raw) > MAX_FILE_BYTES:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
