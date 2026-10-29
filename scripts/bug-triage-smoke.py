"""Run one real triage pass against an allowlisted repository and record evidence."""

import asyncio
import json
import sys
from datetime import UTC, datetime

from google.adk.sessions import InMemorySessionService

from agents.bug_assistant.config import BugSettings
from agents.bug_assistant.models import BugTriageRequest
from agents.bug_assistant.run import PipelineError, run_triage
from packages.agent_core.config import ROOT

EVIDENCE = ROOT / "docs" / "evidence" / "c2-triage-run.json"
DESCRIPTION = (
    "Session identity components are not validated before being used as document path "
    "segments, so a user_id containing a slash can nest one identity's session under "
    "another. Seen when creating a session through the session service."
)


async def execute(request: BugTriageRequest) -> int:
    started = datetime.now(UTC)
    try:
        verified, draft, trace = await run_triage(
            request, session_service=InMemorySessionService(), user_id="c2-smoke"
        )
    except (PipelineError, ValueError) as exc:
        print(f"BLOCKED: {exc}")
        return 2
    EVIDENCE.write_text(
        json.dumps(
            {
                "started_at": started.isoformat(),
                "finished_at": datetime.now(UTC).isoformat(),
                "request": request.model_dump(mode="json"),
                "trace": trace.as_dict(),
                "verified_triage": verified.model_dump(mode="json"),
                "proposed_issue": draft.model_dump(mode="json") if draft else None,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"events={trace.events} mcp_actually_used={trace.mcp_actually_used}")
    print(f"stages={[f'{s.name}:{s.kind}:{s.outcome}' for s in trace.stages]}")
    print(
        f"repository={verified.repository} issues_searched={verified.issues_searched} "
        f"verified_duplicates={len(verified.verified_duplicates)} "
        f"discarded={len(verified.discarded_duplicates)}"
    )
    print(f"severity={verified.report.severity}")
    print(f"draft_offered={draft is not None}")
    print(f"evidence={EVIDENCE.relative_to(ROOT)}")
    if not trace.mcp_actually_used:
        print("BLOCKED: no MCP tool call was observed, so no triage is claimed")
        return 2
    return 0


if __name__ == "__main__":
    allowlist = sorted(
        entry.strip()
        for entry in BugSettings().github_allowed_repositories.split(",")
        if entry.strip()
    )
    if not allowlist:
        print("BLOCKED_GITHUB_ALLOWLIST: set GITHUB_ALLOWED_REPOSITORIES first.")
        raise SystemExit(2)
    target = sys.argv[1] if len(sys.argv) > 1 else allowlist[0]
    owner, _, repo = target.partition("/")
    raise SystemExit(
        asyncio.run(execute(BugTriageRequest(owner=owner, repo=repo, description=DESCRIPTION)))
    )
