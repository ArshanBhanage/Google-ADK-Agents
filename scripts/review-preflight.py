"""Check Part D dependencies. `--pr owner/repo#number` analyses a real pull request."""

import asyncio
import json
import sys
import time
from datetime import UTC, datetime

from agents.code_reviewer.analysis import analyse, ruff_version
from agents.code_reviewer.config import ReviewSettings
from agents.code_reviewer.github import (
    ReviewUnavailable,
    allowed_repositories,
    fetch_file,
    fetch_pull_request,
)
from packages.agent_core.config import ROOT

EVIDENCE = ROOT / "docs" / "evidence" / "d1-review-run.json"


def parse_target(value: str) -> tuple[str, str, int]:
    repository, _, number = value.partition("#")
    owner, _, repo = repository.partition("/")
    if not owner or not repo or not number.isdigit():
        raise ReviewUnavailable(f"Expected owner/repo#number, got {value!r}")
    return owner, repo, int(number)


async def main(target: str | None) -> int:
    settings = ReviewSettings()
    try:
        allowlist = sorted(allowed_repositories(settings))
        if not settings.github_token.get_secret_value():
            raise ReviewUnavailable(
                "BLOCKED_GITHUB_TOKEN: set GITHUB_TOKEN in agents/code_reviewer/.env to a "
                "fine-grained token with read access to Pull Requests and Contents."
            )
        if not allowlist:
            raise ReviewUnavailable(
                "BLOCKED_REVIEW_ALLOWLIST: set GITHUB_ALLOWED_REPOSITORIES in "
                "agents/code_reviewer/.env."
            )
    except ReviewUnavailable as exc:
        print(str(exc))
        return 2
    print(f"ruff={await ruff_version()} allowed_repositories={allowlist}")
    if target is None:
        print("CONFIGURED_NOT_VERIFIED: pass --pr owner/repo#number to analyse a real PR.")
        return 0

    started = datetime.now(UTC)
    try:
        owner, repo, number = parse_target(target)
        clock = time.monotonic()
        pull = await fetch_pull_request(owner, repo, number, settings)
        fetch_ms = round((time.monotonic() - clock) * 1000)
        print(
            f"pull_request={pull.repository}#{pull.number} state={pull.state} "
            f"head={pull.head_sha[:12]} files={len(pull.changed_files)} fetch_ms={fetch_ms}"
        )
        contents: dict[str, str] = {}
        for file in pull.python_files:
            text = await fetch_file(pull.repository, file.path, pull.head_sha, settings)
            if text is not None:
                contents[file.path] = text
        clock = time.monotonic()
        result = await analyse(pull.changed_files, contents)
        analyse_ms = round((time.monotonic() - clock) * 1000)
    except ReviewUnavailable as exc:
        print(f"BLOCKED: {exc}")
        return 2

    in_diff = result.diff_findings
    print(
        f"analysed={len(result.analysed_paths)} unanalysed={len(result.unanalysed)} "
        f"findings={len(result.findings)} in_changed_lines={len(in_diff)} "
        f"analyse_ms={analyse_ms}"
    )
    for finding in in_diff[:8]:
        print(
            f"  {finding.path}:{finding.line} [{finding.severity}] "
            f"{finding.rule} ({finding.source})"
        )
    EVIDENCE.write_text(
        json.dumps(
            {
                "started_at": started.isoformat(),
                "finished_at": datetime.now(UTC).isoformat(),
                "pull_request": {
                    "repository": pull.repository,
                    "number": pull.number,
                    "title": pull.title,
                    "state": pull.state,
                    "author": pull.author,
                    "url": pull.url,
                    "head_sha": pull.head_sha,
                    "base_sha": pull.base_sha,
                },
                "files": [
                    {
                        "path": file.path,
                        "status": file.status,
                        "language": file.language,
                        "additions": file.additions,
                        "deletions": file.deletions,
                        "hunk_ranges": file.hunk_ranges,
                        "added_line_count": len(file.added_lines),
                        "patch_present": file.patch_present,
                    }
                    for file in pull.changed_files
                ],
                "tool_versions": result.tool_versions,
                "findings_in_changed_lines": [vars(f) for f in in_diff],
                "findings_outside_changed_lines": len(result.findings) - len(in_diff),
                "unanalysed": result.unanalysed,
                "notes": result.notes + pull.truncated,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"evidence={EVIDENCE.relative_to(ROOT)}")
    if not pull.head_sha or not pull.changed_files:
        print("BLOCKED: the pull request returned no head commit or no changed files")
        return 2
    print("VERIFIED: authenticated PR retrieval, diff line mapping and real tool analysis.")
    return 0


if __name__ == "__main__":
    arguments = sys.argv[1:]
    chosen = arguments[arguments.index("--pr") + 1] if "--pr" in arguments else None
    raise SystemExit(asyncio.run(main(chosen)))
