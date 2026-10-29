"""ADK review pipeline.

`review_analysis` is a plain BaseAgent: it fetches the pull request, maps the diff, runs
Ruff and the AST parser, and asks the sandbox to run tests or records why it would not.
No model is involved in any of that. `review_reasoner` is the only LlmAgent, and it may
comment solely on lines the analysis stage declared admissible. `review_assembler` is
again plain code: it discards out-of-diff comments, deduplicates, splits verified from
unverified, and refuses an unsupported blocking verdict.
"""

import json
from collections.abc import AsyncGenerator
from typing import Any

from google.adk.agents import Agent, BaseAgent, SequentialAgent
from google.adk.agents.context import Context
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.adk.models.google_llm import Gemini
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

from agents.code_reviewer import prompts
from agents.code_reviewer.analysis import AnalysisResult, Finding, analyse
from agents.code_reviewer.config import COMPONENT, ReviewSettings
from agents.code_reviewer.diff import FileDiff
from agents.code_reviewer.github import PullRequest, fetch_file, fetch_pull_request
from agents.code_reviewer.models import ReviewDraft, ReviewReport, ReviewRequest
from agents.code_reviewer.report import assemble
from agents.code_reviewer.sandbox import TestOutcome, run_tests
from agents.lead_research.agent import DEFAULT_MODEL, RETRY
from packages.agent_core.config import Settings
from packages.agent_core.provider import resolve_backend

MAX_ADMISSIBLE_SHOWN = 400
MAX_EVIDENCE_SHOWN = 60


def require_provider(callback_context: Context) -> None:
    resolve_backend()


def build_model() -> Gemini:
    return Gemini(model=Settings().gemini_model or DEFAULT_MODEL, retry_options=RETRY)


def admissible_summary(files: list[FileDiff]) -> str:
    """The exact lines a comment may refer to, so the reviewer is not guessing."""
    entries = []
    budget = MAX_ADMISSIBLE_SHOWN
    for file in files:
        if not file.hunk_ranges:
            continue
        ranges = ", ".join(f"{start}-{end}" for start, end in file.hunk_ranges)
        entries.append(f"{file.path} ({file.language}): lines {ranges}")
        budget -= 1
        if budget <= 0:
            entries.append("… further files omitted from this listing")
            break
    return "\n".join(entries) or "no changed lines were parseable"


def evidence_summary(findings: list[Finding]) -> str:
    if not findings:
        return "no tool diagnostic landed on a changed line"
    return "\n".join(
        f"{item.path}:{item.line} [{item.severity}] {item.rule} ({item.source}): {item.message}"
        for item in findings[:MAX_EVIDENCE_SHOWN]
    )


class ReviewAnalysis(BaseAgent):
    """Retrieval, diff mapping, real tool runs and the sandbox decision. No model."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        raw = ctx.session.state.get("review_request")
        request = (
            ReviewRequest.model_validate_json(raw)
            if isinstance(raw, str)
            else ReviewRequest.model_validate(raw)
        )
        settings = ReviewSettings()
        pull = await fetch_pull_request(request.owner, request.repo, request.pull_request, settings)
        contents: dict[str, str] = {}
        for file in pull.python_files:
            text = await fetch_file(pull.repository, file.path, pull.head_sha, settings)
            if text is not None:
                contents[file.path] = text
        analysis = await analyse(pull.changed_files, contents)
        # Executing a contributor's tests is refused by policy; see sandbox.py.
        outcome = await run_tests(COMPONENT, authorized=False)

        delta = {
            "pull_request": _pull_state(pull),
            "analysis": _analysis_state(analysis),
            "test_outcome": vars(outcome),
            "admissible_lines": admissible_summary(pull.changed_files),
            "tool_evidence": evidence_summary(analysis.diff_findings),
            "pull_request_summary": (
                f"{pull.repository}#{pull.number} '{pull.title}' by {pull.author} "
                f"[{pull.state}] at {pull.head_sha[:12]}, "
                f"{len(pull.changed_files)} changed file(s)"
            ),
            "test_outcome_summary": f"{outcome.status}: {outcome.reason or 'no reason recorded'}",
        }
        yield Event(
            author=self.name,
            content=types.Content(
                role="model",
                parts=[types.Part(text=json.dumps(delta["pull_request_summary"]))],
            ),
            actions=EventActions(state_delta=delta),
        )


class ReviewAssembler(BaseAgent):
    """Discards, deduplicates and splits the reviewer's comments. No model."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        state = ctx.session.state
        pull = _pull_from_state(state["pull_request"])
        analysis = _analysis_from_state(state["analysis"])
        outcome = TestOutcome(**state["test_outcome"])
        raw = state.get("review_draft")
        draft = (
            ReviewDraft.model_validate_json(raw)
            if isinstance(raw, str)
            else ReviewDraft.model_validate(raw)
        )
        report = assemble(pull, analysis, draft, outcome.status, outcome.reason, outcome.isolation)
        yield Event(
            author=self.name,
            content=types.Content(role="model", parts=[types.Part(text=report.model_dump_json())]),
            actions=EventActions(state_delta={"review_report": report.model_dump(mode="json")}),
        )


def _pull_state(pull: PullRequest) -> dict[str, Any]:
    return {
        "repository": pull.repository,
        "number": pull.number,
        "title": pull.title,
        "state": pull.state,
        "head_sha": pull.head_sha,
        "base_sha": pull.base_sha,
        "author": pull.author,
        "url": pull.url,
        "truncated": pull.truncated,
        "files": [
            {
                "path": f.path,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "hunk_ranges": [list(r) for r in f.hunk_ranges],
                "patch_present": f.patch_present,
            }
            for f in pull.changed_files
        ],
    }


def _pull_from_state(raw: dict[str, Any]) -> PullRequest:
    files = [
        FileDiff(
            path=str(item["path"]),
            status=str(item["status"]),
            additions=int(item["additions"]),
            deletions=int(item["deletions"]),
            hunk_ranges=[(int(a), int(b)) for a, b in item["hunk_ranges"]],
            patch_present=bool(item["patch_present"]),
        )
        for item in raw["files"]
    ]
    return PullRequest(
        repository=str(raw["repository"]),
        number=int(raw["number"]),
        title=str(raw["title"]),
        state=str(raw["state"]),
        head_sha=str(raw["head_sha"]),
        base_sha=str(raw["base_sha"]),
        author=str(raw["author"]),
        url=str(raw["url"]),
        changed_files=files,
        truncated=[str(item) for item in raw["truncated"]],
    )


def _analysis_state(analysis: AnalysisResult) -> dict[str, Any]:
    return {
        "findings": [vars(f) for f in analysis.findings],
        "analysed_paths": analysis.analysed_paths,
        "unanalysed": analysis.unanalysed,
        "tool_versions": analysis.tool_versions,
        "notes": analysis.notes,
    }


def _analysis_from_state(raw: dict[str, Any]) -> AnalysisResult:
    return AnalysisResult(
        findings=[Finding(**item) for item in raw["findings"]],
        analysed_paths=[str(p) for p in raw["analysed_paths"]],
        unanalysed=[str(p) for p in raw["unanalysed"]],
        tool_versions=dict(raw["tool_versions"]),
        notes=[str(n) for n in raw["notes"]],
    )


def build_pipeline() -> SequentialAgent:
    reasoner = Agent(
        name="review_reasoner",
        model=build_model(),
        instruction=prompts.REVIEW,
        output_key="review_draft",
        output_schema=ReviewDraft,
        generate_content_config=types.GenerateContentConfig(
            temperature=0.1, max_output_tokens=8192
        ),
    )
    return SequentialAgent(
        name="review_pipeline",
        input_schema=ReviewRequest,
        description="Review a real pull request with deterministic analysis and ADK synthesis.",
        sub_agents=[
            ReviewAnalysis(name="review_analysis"),
            reasoner,
            ReviewAssembler(name="review_assembler"),
        ],
    )


def build_agent() -> Agent:
    return Agent(
        name="code_reviewer",
        model=build_model(),
        instruction=prompts.SAFETY
        + """
Collect the repository owner, repository name and pull request number, then call
review_pipeline once. Report the summary, the verified findings with their rule codes,
the unverified findings labelled as the reviewer's reading, the test execution status,
and every limitation. Review is read-only: you cannot post a comment, and posting is a
separately authorized action in the application.
""",
        tools=[AgentTool(agent=build_pipeline())],
        before_agent_callback=require_provider,
        generate_content_config=types.GenerateContentConfig(
            temperature=0.1, max_output_tokens=4096
        ),
    )


__all__ = ["ReviewReport", "build_agent", "build_pipeline", "root_agent"]

root_agent = build_agent()
