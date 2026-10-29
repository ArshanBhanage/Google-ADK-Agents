"""Read-only issue tools wrapped so the allowlist and the evidence record are ours.

The MCP server's own tools are called underneath; these wrappers add the repository
allowlist check, a per-session call budget, and a record of exactly which issues came
back. The verification stage later checks the model's claims against that record.
"""

import json
from typing import Any

from google.adk.tools.tool_context import ToolContext

from agents.bug_assistant.config import BugSettings
from agents.bug_assistant.mcp import McpUnavailable, admissible, build_toolset, require_allowed

SEARCH_BUDGET = 6
MAX_ISSUES_RECORDED = 40
# Issue bodies are long and arrive with a lot of API noise; the model sees a bounded
# projection while the full record stays in session state for verification.
BODY_EXCERPT_CHARS = 1200


def _unwrap(raw: Any) -> Any:
    """MCP wraps tool results in a content envelope; take the JSON inside it."""
    text = raw if isinstance(raw, str) else json.dumps(raw, default=str)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict) and isinstance(payload.get("content"), list):
        for part in payload["content"]:
            if isinstance(part, dict) and part.get("type") == "text":
                try:
                    return json.loads(part["text"])
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
    return payload


def _issues_from(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("items", "issues"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def summarise(issue: dict[str, Any]) -> dict[str, Any]:
    """The bounded projection of one issue that the model is allowed to see."""
    body = str(issue.get("body") or "")
    return {
        "number": issue.get("number"),
        "title": str(issue.get("title") or ""),
        "url": str(issue.get("html_url") or issue.get("url") or ""),
        "state": str(issue.get("state") or ""),
        "updated_at": str(issue.get("updated_at") or ""),
        "labels": [
            str(label.get("name", "")) if isinstance(label, dict) else str(label)
            for label in (issue.get("labels") or [])
        ][:10],
        "body_excerpt": body[:BODY_EXCERPT_CHARS],
        "body_truncated": len(body) > BODY_EXCERPT_CHARS,
    }


async def search_repository_issues(
    owner: str, repo: str, query: str, tool_context: ToolContext
) -> dict[str, Any]:
    """Search issues in an allowlisted repository over the real MCP connection.

    Args:
        owner: Repository owner. Must be allowlisted by the operator.
        repo: Repository name. Must be allowlisted by the operator.
        query: Keywords to match against issue titles and bodies.
    """
    used = int(tool_context.state.get("issue_search_count", 0))
    if used >= SEARCH_BUDGET:
        return {
            "status": "BLOCKED",
            "reason": f"Per-session search budget of {SEARCH_BUDGET} reached",
        }
    settings = BugSettings()
    try:
        repository = require_allowed(owner, repo, settings)
    except McpUnavailable as exc:
        return {"status": "BLOCKED", "reason": str(exc)}
    tool_context.state["issue_search_count"] = used + 1

    cleaned = " ".join(query.split())[:200]
    toolset = build_toolset(settings)
    try:
        tools = {tool.name: tool for tool in admissible(await toolset.get_tools())}
        search = tools.get("search_issues")
        if search is None:
            return {"status": "FAILED", "reason": "The server advertises no search_issues tool"}
        raw = await search.run_async(
            args={"query": f"repo:{repository} is:issue {cleaned}".strip(), "perPage": 10},
            tool_context=tool_context,
        )
    except McpUnavailable as exc:
        return {"status": "BLOCKED", "reason": str(exc)}
    except Exception as exc:
        return {"status": "FAILED", "reason": f"{type(exc).__name__}: {str(exc)[:300]}"}
    finally:
        await toolset.close()

    issues = _issues_from(_unwrap(raw))
    record = dict(tool_context.state.get("issue_evidence", {}))
    for issue in issues[:MAX_ISSUES_RECORDED]:
        summary = summarise(issue)
        if isinstance(summary["number"], int):
            record[str(summary["number"])] = summary
    tool_context.state["issue_evidence"] = record
    tool_context.state["issue_repository"] = repository
    return {
        "status": "COMPLETED",
        "repository": repository,
        "query": cleaned,
        "returned": len(issues),
        "issues": [summarise(issue) for issue in issues[:10]],
    }
