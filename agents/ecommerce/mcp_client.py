import asyncio
from typing import Any
from urllib.parse import urlsplit

import httpx2
from google.auth.transport.requests import Request
from google.oauth2.id_token import fetch_id_token
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .config import CommerceSettings

CATALOG_TOOLS = {"search_catalog", "get_product_details"}


async def toolbox_headers(settings: CommerceSettings) -> dict[str, str]:
    if urlsplit(settings.toolbox_url).hostname in {"127.0.0.1", "localhost"}:
        return {}
    if not settings.toolbox_audience:
        raise ValueError(
            "BLOCKED_TOOLBOX_AUTH: set TOOLBOX_AUDIENCE for the private Cloud Run service"
        )
    token = await asyncio.to_thread(fetch_id_token, Request(), settings.toolbox_audience)
    return {"Authorization": "Bearer " + token}


async def probe_toolbox(settings: CommerceSettings) -> dict[str, Any]:
    if not settings.toolbox_url:
        raise ValueError("BLOCKED_TOOLBOX: set TOOLBOX_URL")
    headers = await toolbox_headers(settings)
    async with asyncio.timeout(30), httpx2.AsyncClient(headers=headers, timeout=15) as client:
        async with streamable_http_client(settings.toolbox_url, http_client=client) as (
            read,
            write,
        ):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                listing = await session.list_tools()
                names = {tool.name for tool in listing.tools}
                if names != CATALOG_TOOLS:
                    raise ValueError(
                        "Unexpected MCP tool surface; expected only the catalog toolset"
                    )
                result = await session.call_tool(
                    "search_catalog", {"query": "catalog connectivity check"}
                )
                if result.is_error:
                    raise ValueError("MCP catalog query returned a tool error")
                return {
                    "status": "MCP_QUERY_VERIFIED",
                    "server": initialized.server_info.name,
                    "version": initialized.server_info.version,
                    "tools": sorted(names),
                    "result_blocks": len(result.content),
                    "database_mode": settings.database_mode,
                    "note": "A successful empty query does not verify merchant synchronization.",
                }


async def call_catalog(
    settings: CommerceSettings, tool: str, arguments: dict[str, str]
) -> dict[str, Any]:
    """Return actual MCP content without substituting generated catalog rows."""
    import json

    if tool not in CATALOG_TOOLS:
        raise ValueError("Tool not allowed")
    async with (
        asyncio.timeout(30),
        httpx2.AsyncClient(headers=await toolbox_headers(settings), timeout=15) as client,
    ):
        async with streamable_http_client(settings.toolbox_url, http_client=client) as (
            read,
            write,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments)
                if result.is_error:
                    raise ValueError("Catalog tool failed")
                rows: list[dict[str, Any]] = []
                for block in result.content:
                    if block.type == "text":
                        value = json.loads(block.text)
                        if isinstance(value, list):
                            rows.extend(value)
                        elif isinstance(value, dict):
                            rows.append(value)
                return {
                    "products": rows,
                    "source": "PostgreSQL via MCP Toolbox",
                    "inventory": "Imported snapshot; refreshed before checkout",
                }
