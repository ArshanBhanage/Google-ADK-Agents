"""Deterministic check that a CLI answer refers to files that actually exist.

The CLI is the only component that saw the workspace, so its answer is the one thing
in this pipeline that cannot be taken on trust. This stage is plain code rather than
a model, for the same reason Part A's ranker is: a model must not be the judge of
whether its own output is grounded.
"""

import re
from pathlib import Path

from agents.gemini_cli_tool.models import GroundingCheck

# A path-like token: at least one separator or a known source extension, no spaces.
PATH_PATTERN = re.compile(
    r"(?<![\w/.])((?:[\w.-]+/)+[\w.-]+\.\w{1,6}|[\w.-]+\.(?:py|ts|tsx|js|jsonc?|ya?ml|toml|md|sql|sh))(?![\w/])"
)
MAX_CLAIMS = 60


def extract_paths(answer: str) -> list[str]:
    """Collect distinct path-like tokens, preserving the order they are mentioned."""
    seen: dict[str, None] = {}
    for match in PATH_PATTERN.finditer(answer):
        candidate = match.group(1).strip("`'\",.()[]")
        if candidate and candidate not in seen:
            seen[candidate] = None
        if len(seen) >= MAX_CLAIMS:
            break
    return list(seen)


def resolve_within(workspace: Path, claim: str) -> Path | None:
    """Resolve a claimed path under the workspace, refusing any escape from it."""
    if claim.startswith("/") or ".." in Path(claim).parts:
        return None
    try:
        candidate = (workspace / claim).resolve()
    except (OSError, ValueError):
        return None
    try:
        candidate.relative_to(workspace.resolve())
    except ValueError:
        return None
    return candidate


def check_grounding(answer: str, workspace: Path) -> GroundingCheck:
    claimed = extract_paths(answer)
    present: list[str] = []
    absent: list[str] = []
    for claim in claimed:
        resolved = resolve_within(workspace, claim)
        if resolved is not None and resolved.exists():
            present.append(claim)
            continue
        # A bare filename may legitimately refer to a nested file the answer named
        # without its directory, so search before declaring it absent.
        name = Path(claim).name
        if "/" not in claim and any(workspace.rglob(name)):
            present.append(claim)
        else:
            absent.append(claim)

    limitations: list[str] = []
    if not claimed:
        limitations.append(
            "The answer named no file, so it could not be checked against the workspace."
        )
    if absent:
        limitations.append(
            f"{len(absent)} named path(s) do not exist in the inspected workspace: "
            + ", ".join(absent[:8])
        )
    if len(claimed) >= MAX_CLAIMS:
        limitations.append(f"Only the first {MAX_CLAIMS} named paths were checked.")
    limitations.append(
        "Path existence is verified; the accuracy of statements about file contents is not."
    )
    return GroundingCheck(
        paths_claimed=claimed,
        paths_present=present,
        paths_absent=absent,
        grounded=bool(present) and not absent,
        limitations=limitations,
    )
