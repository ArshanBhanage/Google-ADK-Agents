"""Resolve which Gemini backend is configured and fail closed before a billable call.

Two backends reach the same models on different billing tracks. The Gemini Developer
API (AI Studio key) bills on its own pipeline, which Google Cloud Free Trial credits
do not cover. Vertex AI bills to the Cloud project, where promotional credits apply.
The choice is therefore a cost decision as much as a technical one, so it is explicit
configuration rather than an inferred default.
"""

import os
from dataclasses import dataclass

import google.auth
from google.auth.exceptions import DefaultCredentialsError

from packages.agent_core.config import Settings

CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
ADC_GUIDANCE = (
    "BLOCKED_ADC: Vertex AI needs application default credentials and none resolved.\n"
    "  1. Install the gcloud CLI: https://cloud.google.com/sdk/docs/install\n"
    "  2. gcloud auth login\n"
    "  3. gcloud config set project <GOOGLE_CLOUD_PROJECT>\n"
    "  4. gcloud services enable aiplatform.googleapis.com\n"
    "  5. gcloud auth application-default login\n"
    "Credentials are read from the local ADC file; no key material enters this repo."
)


class ProviderUnavailable(ValueError):
    """Required provider configuration or credentials are absent."""


@dataclass(frozen=True)
class Backend:
    """What was configured. Carries no credential material."""

    name: str
    model: str
    project: str = ""
    location: str = ""

    @property
    def uses_vertex(self) -> bool:
        return self.name == "vertex_ai"

    def describe(self) -> str:
        where = f" project={self.project} location={self.location}" if self.uses_vertex else ""
        return f"backend={self.name} model={self.model}{where}"


def resolve_backend(settings: Settings | None = None) -> Backend:
    """Validate configuration, export what the genai client reads, and report the choice."""
    config = settings or Settings()
    if not config.gemini_model:
        raise ProviderUnavailable("BLOCKED: set GEMINI_MODEL in root .env")

    if not config.google_genai_use_vertexai:
        key = config.google_api_key.get_secret_value()
        if not key:
            raise ProviderUnavailable(
                "BLOCKED: set GOOGLE_API_KEY in root .env, or set "
                "GOOGLE_GENAI_USE_VERTEXAI=TRUE to bill Vertex AI against Cloud credits."
            )
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"
        os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] = "FALSE"
        os.environ["GOOGLE_API_KEY"] = key
        return Backend(name="gemini_api", model=config.gemini_model)

    missing = [
        name
        for name, value in (
            ("GOOGLE_CLOUD_PROJECT", config.google_cloud_project),
            ("GOOGLE_CLOUD_LOCATION", config.google_cloud_location),
        )
        if not value
    ]
    if missing:
        raise ProviderUnavailable(f"BLOCKED: set {', '.join(missing)} in root .env")
    try:
        google.auth.default(scopes=[CLOUD_PLATFORM_SCOPE])
    except DefaultCredentialsError as exc:
        raise ProviderUnavailable(ADC_GUIDANCE) from exc

    # An API key left in .env must not reach a Vertex call; the backends authenticate
    # differently and a stray key silently changes which account is billed.
    # Installed ADK 2.13.0 still reads GOOGLE_GENAI_USE_VERTEXAI but warns that
    # GOOGLE_GENAI_USE_ENTERPRISE supersedes it. Both are set so the behaviour does
    # not change silently when the deprecated name is removed.
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE"
    os.environ["GOOGLE_GENAI_USE_ENTERPRISE"] = "TRUE"
    os.environ["GOOGLE_CLOUD_PROJECT"] = config.google_cloud_project
    os.environ["GOOGLE_CLOUD_LOCATION"] = config.google_cloud_location
    os.environ.pop("GOOGLE_API_KEY", None)
    os.environ.pop("GEMINI_API_KEY", None)
    return Backend(
        name="vertex_ai",
        model=config.gemini_model,
        project=config.google_cloud_project,
        location=config.google_cloud_location,
    )
