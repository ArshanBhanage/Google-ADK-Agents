"""Run one real lead-research query and record sanitized evidence of the run."""

import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from google.adk.sessions import InMemorySessionService

from agents.lead_research.models import LeadReport, ResearchRequest
from agents.lead_research.run import PipelineError, ResearchTrace, run_research
from packages.agent_core.config import ROOT

EVIDENCE = ROOT / "docs" / "evidence" / "a1-live-grounded-run.json"


async def execute(request: ResearchRequest) -> tuple[LeadReport, ResearchTrace]:
    return await run_research(request, session_service=InMemorySessionService(), user_id="a1-smoke")


def main(path: Path) -> int:
    request = ResearchRequest.model_validate_json(path.read_text())
    started = datetime.now(UTC)
    try:
        report, trace = asyncio.run(execute(request))
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
                "report": report.model_dump(mode="json"),
            },
            indent=2,
        )
        + "\n"
    )
    print(f"events={trace.events} search_used={trace.used_google_search}")
    print(f"retrieved_sources={len(trace.retrieved_sources)} verified_leads={len(report.leads)}")
    print(
        f"usage: prompt={trace.prompt_tokens} output={trace.output_tokens} "
        f"thoughts={trace.thought_tokens} billable_searches={trace.billable_searches}"
    )
    print(f"evidence={EVIDENCE.relative_to(ROOT)}")
    if not trace.used_google_search:
        print("BLOCKED: the run completed without any observed Google Search grounding")
        return 2
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m scripts.lead-live-smoke <request.json>")
        raise SystemExit(2)
    raise SystemExit(main(Path(sys.argv[1])))
