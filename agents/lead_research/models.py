from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    industry: str = Field(min_length=2, max_length=160)
    region: str = Field(min_length=2, max_length=160)
    buyer_profile: str = Field(min_length=5, max_length=1000)
    quantity: int = Field(ge=1, le=10)
    exclusions: list[str] = Field(default_factory=list, max_length=30)


class Citation(BaseModel):
    url: str
    retrieved_at: datetime
    excerpt: str = Field(min_length=1, max_length=1200)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("url")
    @classmethod
    def https_only(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Citation must use a public HTTPS URL without credentials")
        return value


class Lead(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    domain: str = Field(min_length=3, max_length=253)
    match_explanation: str = Field(max_length=2000)
    score: int = Field(default=0, ge=0, le=100)
    confidence: Literal["low", "medium", "high"]
    verification: Literal["unverified", "source_retrieved"]
    citations: list[Citation] = Field(default_factory=list, max_length=10)


class LeadReport(BaseModel):
    leads: list[Lead] = Field(default_factory=list, max_length=10)
    limitations: list[str]


class SourcePage(BaseModel):
    url: str
    retrieved_at: datetime
    title: str
    text: str
    content_sha256: str
