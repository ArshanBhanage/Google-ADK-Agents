from typing import Any

from google.adk.tools.tool_context import ToolContext

from agents.gemini_cli_tool.cli import CliError, resolve_workspace, run_cli

CALL_BUDGET = 3


async def inspect_workspace_with_gemini_cli(task: str, tool_context: ToolContext) -> dict[str, Any]:
    """Run the real Gemini CLI against the authorized read-only workspace.

    Args:
        task: A self-contained instruction describing what to inspect and report.
    """
    used = int(tool_context.state.get("cli_call_count", 0))
    if used >= CALL_BUDGET:
        return {"status": "BLOCKED", "reason": f"Per-session CLI budget of {CALL_BUDGET} reached"}
    tool_context.state["cli_call_count"] = used + 1
    try:
        invocation = await run_cli(task)
    except CliError as exc:
        # Reported as a failed tool outcome so the trace keeps it; never a fabricated answer.
        return {"status": "FAILED", "reason": str(exc)[:600]}
    record = invocation.as_dict()
    tool_context.state["cli_invocation"] = record
    tool_context.state["cli_workspace"] = str(resolve_workspace())
    return {"status": "COMPLETED", **record}
