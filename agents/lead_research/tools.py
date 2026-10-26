import asyncio
from typing import Any

from google.adk.tools.tool_context import ToolContext

from agents.lead_research.sources import PublicWebsiteSource, SourceError

_source_slots = asyncio.Semaphore(1)


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
    return {"status": "RETRIEVED", **page.model_dump(mode="json")}
