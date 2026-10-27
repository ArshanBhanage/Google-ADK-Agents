import asyncio
from typing import Any

from google.adk.tools.tool_context import ToolContext

from agents.lead_research.models import SourcePage
from agents.lead_research.sources import PublicWebsiteSource, SourceError

_source_slots = asyncio.Semaphore(1)

# Tool output is re-sent on every later turn of the validator loop, so the page text
# returned to the model is the dominant input cost. The full text is kept in session
# state for deterministic verification; the model only needs enough to quote from.
MODEL_EXCERPT_CHARS = 3000


def model_view(page: SourcePage) -> dict[str, Any]:
    """The bounded projection of a retrieved page that the model is allowed to see."""
    excerpt = page.text[:MODEL_EXCERPT_CHARS]
    return {
        "url": page.url,
        "retrieved_at": page.retrieved_at.isoformat(),
        "title": page.title,
        "content_sha256": page.content_sha256,
        "text_excerpt": excerpt,
        "retrieved_chars": len(page.text),
        "excerpt_truncated": len(page.text) > len(excerpt),
    }


async def inspect_public_source(url: str, tool_context: ToolContext) -> dict[str, Any]:
    """Retrieve a public source subject to robots, TLS, SSRF and response-size limits."""
    count = int(tool_context.state.get("source_fetch_count", 0))
    if count >= 15:
        return {"status": "BLOCKED", "reason": "Per-session source retrieval budget reached"}
    tool_context.state["source_fetch_count"] = count + 1
    try:
        async with _source_slots:
            await asyncio.sleep(1)
            page = await PublicWebsiteSource().fetch(url)
    except (SourceError, TimeoutError) as exc:
        return {"status": "UNVERIFIED", "reason": str(exc) or "Source timed out"}
    evidence = dict(tool_context.state.get("source_evidence", {}))
    evidence[page.url] = page.model_dump(mode="json")
    tool_context.state["source_evidence"] = evidence
    return {"status": "RETRIEVED", **model_view(page)}
