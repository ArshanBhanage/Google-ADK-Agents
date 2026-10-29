from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["critical", "high", "medium", "low"]


class BugTriageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    owner: str = Field(min_length=1, max_length=39, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")
    repo: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    description: str = Field(min_length=20, max_length=4000)


class DuplicateCandidate(BaseModel):
    """A possible duplicate. `number` and `url` must come from tool output, never
    from the model's recollection; the deterministic stage drops anything unmatched."""

    number: int
    title: str
    url: str
    state: str
    updated_at: str
    why_similar: str


class TriageReport(BaseModel):
    """Kept free of regex and item constraints, which Vertex rejects in a response
    schema; see docs/technical-decisions.md."""

    severity: Severity
    severity_rationale: str
    root_cause_hypothesis: str
    reproduction_steps: list[str]
    debugging_checklist: list[str]
    duplicate_candidates: list[DuplicateCandidate]
    next_action: str
    limitations: list[str]


class VerifiedTriage(BaseModel):
    """What survived verification against real issue data."""

    report: TriageReport
    verified_duplicates: list[DuplicateCandidate]
    discarded_duplicates: list[str]
    repository: str
    issues_searched: int


class ProposedIssue(BaseModel):
    """The exact content a write would create. Hashed so approval binds to it.

    Owner and repo are constrained here as well as on the request, because this model
    is what reaches the write call and may be rebuilt from state or model output.
    """

    model_config = ConfigDict(extra="forbid")
    owner: str = Field(min_length=1, max_length=39, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]*$")
    repo: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    title: str = Field(min_length=10, max_length=256)
    body: str = Field(min_length=20, max_length=60000)


class CreatedIssue(BaseModel):
    number: int
    url: str
    state: str
