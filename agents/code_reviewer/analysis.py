"""Deterministic analysis: real Ruff diagnostics and real AST parsing.

No model is involved here. Every finding carries a rule code from a tool that actually
ran, and is attributed only to a line the pull request touched. Languages without a
configured tool are reported as unanalysed rather than reviewed by assertion.
"""

import ast
import asyncio
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from agents.code_reviewer.diff import FileDiff

RUFF_TIMEOUT = 120.0
# Only Python has a configured analyser in this project. Claiming to review a language
# with a linter that is not installed would be a fabricated capability.
ANALYSED_LANGUAGES = frozenset({"python"})


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    message: str
    source: str
    severity: str
    in_diff: bool


@dataclass
class AnalysisResult:
    findings: list[Finding]
    analysed_paths: list[str]
    unanalysed: list[str]
    tool_versions: dict[str, str]
    notes: list[str]

    @property
    def diff_findings(self) -> list[Finding]:
        return [finding for finding in self.findings if finding.in_diff]


async def ruff_version() -> str:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "ruff",
        "--version",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    out, _ = await process.communicate()
    return out.decode().strip() or "unknown"


def syntax_findings(path: str, text: str, diff: FileDiff) -> list[Finding]:
    """A file that does not parse is the one finding worth reporting unconditionally."""
    try:
        ast.parse(text, filename=path)
    except SyntaxError as exc:
        line = exc.lineno or 1
        return [
            Finding(
                path=path,
                line=line,
                rule="syntax-error",
                message=(exc.msg or "invalid syntax"),
                source="python-ast",
                severity="critical",
                in_diff=diff.in_diff(line),
            )
        ]
    return []


async def run_ruff(directory: Path, paths: list[str]) -> tuple[list[dict[str, object]], str]:
    """Run the real Ruff binary over materialised files and read its JSON output."""
    if not paths:
        return [], ""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--output-format",
        "json",
        "--no-cache",
        # The reviewed project's own configuration is deliberately not loaded: a pull
        # request could otherwise disable the checks that would flag it.
        "--isolated",
        "--select",
        "E,F,I,UP,B,ASYNC,S,BLE,A001,C4,T20,RET,SIM,PTH",
        *paths,
        cwd=str(directory),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), timeout=RUFF_TIMEOUT)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise RuntimeError("Ruff exceeded its time budget") from None
    text = out.decode("utf-8", "replace").strip()
    if not text:
        return [], err.decode("utf-8", "replace")[:400]
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return [], err.decode("utf-8", "replace")[:400] or "Ruff produced unparseable output"
    return (payload if isinstance(payload, list) else []), ""


SEVERITY_BY_PREFIX = {
    "E9": "critical",
    "F8": "high",
    "F4": "medium",
    "F": "high",
    "S": "high",
    "B": "medium",
    "ASYNC": "high",
    "BLE": "medium",
    "T20": "low",
    "E": "low",
    "I": "low",
    "UP": "low",
    "RET": "low",
    "SIM": "low",
    "C4": "low",
    "PTH": "low",
}


def severity_for(rule: str) -> str:
    for prefix in sorted(SEVERITY_BY_PREFIX, key=len, reverse=True):
        if rule.startswith(prefix):
            return SEVERITY_BY_PREFIX[prefix]
    return "medium"


def is_test_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (
        "/tests/" in f"/{path}"
        or "/test/" in f"/{path}"
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


# Rules that are correct in application code but noise in a test suite. Reporting
# `assert` as a finding in a test file would make the review look like it does not know
# what it is reading, so these are dropped there rather than downgraded.
TEST_FILE_EXEMPT_RULES = frozenset({"S101", "S105", "S106", "S107", "PLR2004", "T201"})


def admissible_rule(rule: str, path: str) -> bool:
    return not (is_test_file(path) and rule in TEST_FILE_EXEMPT_RULES)


async def analyse(files: list[FileDiff], contents: dict[str, str]) -> AnalysisResult:
    """Materialise the changed files and run the configured tools over them."""
    findings: list[Finding] = []
    notes: list[str] = []
    exempted = 0
    analysed: list[str] = []
    unanalysed: list[str] = []
    by_path = {file.path: file for file in files}

    for file in files:
        if file.language not in ANALYSED_LANGUAGES:
            unanalysed.append(
                f"{file.path} ({file.language}): no analyser is configured for this "
                "language in this project"
            )
        elif file.path not in contents:
            unanalysed.append(f"{file.path}: content could not be retrieved at the head commit")

    with tempfile.TemporaryDirectory(prefix="review-") as workspace:
        directory = Path(workspace)
        materialised: list[str] = []
        for path, text in contents.items():
            changed = by_path.get(path)
            if changed is None or changed.language not in ANALYSED_LANGUAGES:
                continue
            target = directory / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            materialised.append(path)
            findings.extend(syntax_findings(path, text, changed))

        diagnostics, error = await run_ruff(directory, materialised)
        if error:
            notes.append(f"Ruff reported on stderr: {error}")
        analysed = materialised

    for item in diagnostics:
        filename = str(item.get("filename", ""))
        relative = filename.split("/review-", 1)[-1]
        for candidate in materialised:
            if filename.endswith(candidate):
                relative = candidate
                break
        changed = by_path.get(relative)
        location = item.get("location")
        line = int(location.get("row", 1)) if isinstance(location, dict) else 1
        rule = str(item.get("code") or "ruff")
        if not admissible_rule(rule, relative):
            exempted += 1
            continue
        findings.append(
            Finding(
                path=relative,
                line=line,
                rule=rule,
                message=str(item.get("message", "")),
                source="ruff",
                severity=severity_for(rule),
                in_diff=changed.in_diff(line) if changed else False,
            )
        )

    if exempted:
        notes.append(
            f"{exempted} diagnostic(s) were dropped as expected in test files, such as "
            "`assert` usage, rather than reported as defects."
        )
    outside = len(findings) - len([f for f in findings if f.in_diff])
    if outside:
        notes.append(
            f"{outside} finding(s) fell outside the changed lines and are reported "
            "separately; a review must not comment on code this pull request did not touch."
        )
    notes.append(
        "Static analysis only. No test suite was executed, so no behavioural claim is made."
    )
    return AnalysisResult(
        findings=sorted(findings, key=lambda f: (f.path, f.line, f.rule)),
        analysed_paths=analysed,
        unanalysed=unanalysed,
        tool_versions={"ruff": await ruff_version(), "python-ast": sys.version.split()[0]},
        notes=notes,
    )
