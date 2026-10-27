"""Run one real B2 pipeline pass and record sanitized evidence."""

import asyncio
import json
import sys
from datetime import UTC, datetime

from google.adk.sessions import InMemorySessionService

from agents.gemini_cli_tool.run import PipelineError, run_cli_pipeline
from packages.agent_core.config import ROOT

EVIDENCE = ROOT / "docs" / "evidence" / "b2-pipeline-run.json"
QUESTION = (
    "Explain how this project loads configuration and authenticates requests, "
    "citing the exact files you inspected."
)


async def execute(question: str) -> int:
    started = datetime.now(UTC)
    try:
        answer, grounding, plan, trace = await run_cli_pipeline(
            question, session_service=InMemorySessionService(), user_id="b2-smoke"
        )
    except (PipelineError, ValueError) as exc:
        print(f"BLOCKED: {exc}")
        return 2
    EVIDENCE.write_text(
        json.dumps(
            {
                "started_at": started.isoformat(),
                "finished_at": datetime.now(UTC).isoformat(),
                "question": question,
                "plan": plan.model_dump(mode="json") if plan else None,
                "trace": trace.as_dict(),
                "grounding": grounding.model_dump(mode="json"),
                "answer": answer.model_dump(mode="json"),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"events={trace.events} cli_actually_ran={trace.cli_actually_ran}")
    print(f"stages={[f'{s.name}:{s.kind}' for s in trace.stages]}")
    print(
        f"grounded={grounding.grounded} present={len(grounding.paths_present)} "
        f"absent={len(grounding.paths_absent)}"
    )
    print(f"evidence={EVIDENCE.relative_to(ROOT)}")
    if not trace.cli_actually_ran:
        print("BLOCKED: the Gemini CLI subprocess did not complete successfully")
        return 2
    return 0


if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else QUESTION
    raise SystemExit(asyncio.run(execute(question)))
