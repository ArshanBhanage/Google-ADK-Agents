"""Check Part B dependencies. `--live` additionally runs one real CLI invocation."""

import asyncio
import sys

from agents.gemini_cli_tool.cli import CliError, cli_version, run_cli
from packages.agent_core.config import Settings
from packages.agent_core.provider import ProviderUnavailable, resolve_backend

TASK = "List the files in this directory and state what the project does, briefly."


async def main(live: bool) -> int:
    settings = Settings()
    try:
        version = await cli_version(settings)
    except (CliError, TimeoutError) as exc:
        print(str(exc))
        return 2
    print(f"gemini_cli_version={version}")
    try:
        backend = resolve_backend(settings)
        workspace = settings.gemini_workspace.strip() or "<unset>"
    except ProviderUnavailable as exc:
        print(str(exc))
        return 2
    print(f"{backend.describe()} workspace={workspace}")
    if not live:
        print("CONFIGURED_NOT_VERIFIED: run `make verify-cli` to invoke the executable.")
        return 0
    try:
        invocation = await run_cli(TASK, settings=settings)
    except CliError as exc:
        print(f"BLOCKED: {exc}")
        return 2
    print(
        f"VERIFIED: exit={invocation.exit_code} duration_ms={invocation.duration_ms} "
        f"session={invocation.session_id or 'unreported'} "
        f"response_chars={len(invocation.response)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(live="--live" in sys.argv[1:])))
