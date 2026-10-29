"""Unified diff parsing and new-side line mapping.

This is what makes "findings tied to a real file and line" enforceable rather than
aspirational. A finding is only admissible if its line number is one the patch actually
added or modified on the new side of the diff, so a reviewer cannot comment on code the
pull request never touched.
"""

import re
from dataclasses import dataclass, field
from typing import Any

HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


@dataclass
class FileDiff:
    path: str
    status: str
    additions: int
    deletions: int
    # New-side line number -> the added line's text. Context lines are excluded.
    added_lines: dict[int, str] = field(default_factory=dict)
    # Hunk ranges on the new side, used to decide what a review may refer to.
    hunk_ranges: list[tuple[int, int]] = field(default_factory=list)
    patch_present: bool = True

    @property
    def language(self) -> str:
        suffix = self.path.rsplit(".", 1)[-1].lower() if "." in self.path else ""
        return {
            "py": "python",
            "pyi": "python",
            "ts": "typescript",
            "tsx": "typescript",
            "js": "javascript",
            "jsx": "javascript",
            "json": "json",
            "yaml": "yaml",
            "yml": "yaml",
            "toml": "toml",
            "md": "markdown",
            "sql": "sql",
            "sh": "shell",
        }.get(suffix, "other")

    def in_diff(self, line: int) -> bool:
        return any(start <= line <= end for start, end in self.hunk_ranges)


def parse_patch(patch: str | None) -> tuple[dict[int, str], list[tuple[int, int]]]:
    """Walk the hunks, tracking the new-side line counter.

    GitHub omits `patch` for binary files and for files above its size limit, which is
    reported rather than treated as an empty change.
    """
    if not patch:
        return {}, []
    added: dict[int, str] = {}
    ranges: list[tuple[int, int]] = []
    new_line = 0
    hunk_start = 0
    for raw in patch.splitlines():
        header = HUNK.match(raw)
        if header:
            # new_line points at the next unconsumed line, so the hunk ends one before.
            if hunk_start and new_line - 1 >= hunk_start:
                ranges.append((hunk_start, new_line - 1))
            new_line = int(header.group(1))
            hunk_start = new_line
            continue
        if not hunk_start:
            continue
        if raw.startswith("+"):
            added[new_line] = raw[1:]
            new_line += 1
        elif raw.startswith("-"):
            continue
        elif raw.startswith("\\"):
            # "\ No newline at end of file" advances nothing.
            continue
        else:
            new_line += 1
    if hunk_start and new_line - 1 >= hunk_start:
        ranges.append((hunk_start, new_line - 1))
    return added, ranges


def build_file_diff(entry: dict[str, Any]) -> FileDiff:
    """Build from one element of GitHub's pull request files response."""
    path = str(entry.get("filename", ""))
    patch = entry.get("patch")
    added, ranges = parse_patch(patch if isinstance(patch, str) else None)
    return FileDiff(
        path=path,
        status=str(entry.get("status", "")),
        additions=int(entry.get("additions", 0) or 0),
        deletions=int(entry.get("deletions", 0) or 0),
        added_lines=added,
        hunk_ranges=ranges,
        patch_present=isinstance(patch, str) and bool(patch),
    )


def safe_path(path: str) -> bool:
    """Reject anything that could escape a working directory when materialised."""
    if not path or path.startswith("/") or "\\" in path:
        return False
    parts = path.split("/")
    return ".." not in parts and "" not in parts and not any(p.startswith("~") for p in parts)
