"""Run one real review pipeline pass and record sanitized evidence."""

import asyncio
import json
import sys
from datetime import UTC, datetime

from google.adk.sessions import InMemorySessionService

from agents.code_reviewer.models import ReviewRequest
from agents.code_reviewer.report import to_markdown
from agents.code_reviewer.run import PipelineError, run_review
from packages.agent_core.config import ROOT

EVIDENCE = ROOT / "docs" / "evidence" / "d2-review-run.json"
MARKDOWN = ROOT / "docs" / "evidence" / "d2-review-report.md"


async def execute(request: ReviewRequest) -> int:
    started = datetime.now(UTC)
    try:
        report, trace = await run_review(
            request, session_service=InMemorySessionService(), user_id="d2-smoke"
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
                "report": report.model_dump(mode="json"),
            },
            indent=2,
        )
        + "\n"
    )
    MARKDOWN.write_text(to_markdown(report))
    print(f"events={trace.events} stages={[f'{s.name}:{s.kind}' for s in trace.stages]}")
    print(f"pull_request={report.repository}#{report.pull_request} head={report.head_sha[:12]}")
    print(
        f"verified={len(report.verified_comments)} unverified={len(report.unverified_comments)} "
        f"discarded={len(report.discarded_comments)} blocking={report.blocking}"
    )
    print(f"tool_evidence={len(report.tool_evidence)} outside_diff={report.evidence_outside_diff}")
    print(f"test_status={report.test_status}")
    print(f"evidence={EVIDENCE.relative_to(ROOT)} markdown={MARKDOWN.relative_to(ROOT)}")
    if not report.head_sha:
        print("BLOCKED: no head commit was recorded, so no review is claimed")
        return 2
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or "#" not in sys.argv[1]:
        print("usage: python -m scripts.review-smoke owner/repo#number")
        raise SystemExit(2)
    repository, _, number = sys.argv[1].partition("#")
    owner, _, repo = repository.partition("/")
    raise SystemExit(
        asyncio.run(execute(ReviewRequest(owner=owner, repo=repo, pull_request=int(number))))
    )
