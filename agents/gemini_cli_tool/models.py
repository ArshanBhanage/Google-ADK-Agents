from pydantic import BaseModel, ConfigDict, Field


class CliRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=10, max_length=2000)


class CliPlan(BaseModel):
    """What the ADK planning step decided, before any subprocess runs.

    Kept free of constraints that Vertex rejects in a response schema, as recorded in
    docs/technical-decisions.md for Part A.
    """

    task: str
    rationale: str
    expected_evidence: list[str]


class GroundingCheck(BaseModel):
    """Deterministic verdict on whether the CLI answer matches the real workspace."""

    paths_claimed: list[str]
    paths_present: list[str]
    paths_absent: list[str]
    grounded: bool
    limitations: list[str]


class CliAnswer(BaseModel):
    answer: str
    limitations: list[str]
