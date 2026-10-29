from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["critical", "high", "medium", "low"]
Category = Literal["correctness", "security", "performance", "maintainability", "style"]


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    owner: str = Field(min_length=1, max_length=39, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")
    repo: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    pull_request: int = Field(ge=1, le=10_000_000)


class ReviewComment(BaseModel):
    """A reviewer's judgement about one changed line.

    `verified` distinguishes a finding backed by a tool that ran from one the reviewer
    inferred by reading. Nothing here may invent a file or a line: the deterministic
    stage supplies the admissible set and unmatched comments are discarded.
    """

    path: str
    line: int
    severity: Severity
    category: Category
    finding: str
    recommendation: str
    confidence: Literal["high", "medium", "low"]
    rule: str = ""


class ReviewDraft(BaseModel):
    """What the reviewer model proposes. Deliberately free of regex and item caps,
    which Vertex rejects in a response schema."""

    summary: str
    comments: list[ReviewComment]
    blocking: bool
    limitations: list[str]


class ToolEvidence(BaseModel):
    path: str
    line: int
    rule: str
    message: str
    source: str
    severity: str


class ReviewReport(BaseModel):
    """The machine-readable report. The UI renders this; nothing is formatted twice."""

    repository: str
    pull_request: int
    title: str
    head_sha: str
    url: str
    summary: str
    blocking: bool
    verified_comments: list[ReviewComment]
    unverified_comments: list[ReviewComment]
    discarded_comments: list[str]
    tool_evidence: list[ToolEvidence]
    evidence_outside_diff: int
    files_analysed: list[str]
    files_unanalysed: list[str]
    tool_versions: dict[str, str]
    test_status: str
    test_reason: str
    test_isolation: dict[str, str]
    limitations: list[str]
