"""Check Part C dependencies. `--live` performs a real MCP handshake and lookup."""

import asyncio
import json
import sys
import time

from agents.bug_assistant.config import BugSettings
from agents.bug_assistant.mcp import (
    READ_ONLY_TOOLS,
    McpUnavailable,
    admissible,
    allowed_repositories,
    build_toolset,
    validate_url,
)


async def main(live: bool) -> int:
    settings = BugSettings()
    try:
        url = validate_url(settings.github_mcp_url)
        allowlist = sorted(allowed_repositories(settings))
        if not settings.github_token.get_secret_value():
            raise McpUnavailable(
                "BLOCKED_GITHUB_TOKEN: set GITHUB_TOKEN in the local root .env to a "
                "fine-grained token with read-only Issues access."
            )
        if not allowlist:
            raise McpUnavailable(
                "BLOCKED_GITHUB_ALLOWLIST: set GITHUB_ALLOWED_REPOSITORIES in root .env."
            )
    except McpUnavailable as exc:
        print(str(exc))
        return 2
    print(f"transport=streamable_http url={url}")
    print(f"allowed_repositories={allowlist}")
    if not live:
        print("CONFIGURED_NOT_VERIFIED: run `make verify-bug` for a real handshake.")
        return 0

    toolset = build_toolset(settings)
    try:
        started = time.monotonic()
        advertised = await toolset.get_tools()
        handshake_ms = round((time.monotonic() - started) * 1000)
        names = sorted(tool.name for tool in advertised)
        print(f"handshake_ms={handshake_ms} advertised={len(names)} tools={names}")
        usable = admissible(advertised)
        print(f"admitted={sorted(tool.name for tool in usable)}")
        missing = READ_ONLY_TOOLS - set(names)
        if missing:
            print(f"NOTE: expected read tools not advertised: {sorted(missing)}")
        search = next((tool for tool in usable if tool.name == "search_issues"), None)
        if search is None:
            print("BLOCKED: the server advertised no search_issues tool.")
            return 2
        owner, repo = allowlist[0].split("/")
        started = time.monotonic()
        raw = await search.run_async(
            args={"query": f"repo:{owner}/{repo} is:issue", "perPage": 1},
            tool_context=None,  # type: ignore[arg-type]
        )
        lookup_ms = round((time.monotonic() - started) * 1000)
        payload = json.dumps(raw, default=str) if not isinstance(raw, str) else raw
        print(f"lookup_ms={lookup_ms} response_chars={len(payload)} repository={owner}/{repo}")
        if "total_count" not in payload and "items" not in payload:
            print("BLOCKED: the search response did not contain issue data.")
            return 2
    except McpUnavailable as exc:
        print(f"BLOCKED: {exc}")
        return 2
    except Exception as exc:  # the MCP client raises transport-specific errors
        print(f"BLOCKED_MCP_TRANSPORT: {type(exc).__name__}: {str(exc)[:400]}")
        return 2
    finally:
        await toolset.close()
    print("VERIFIED: MCP handshake, read-only tool scope and a real issue lookup.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(live="--live" in sys.argv[1:])))
