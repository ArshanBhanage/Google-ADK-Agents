from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
AGENTS = {
    "lead_research": "A · Deep research lead generation",
    "gemini_cli_tool": "B · Gemini CLI pipeline",
    "bug_assistant": "C · MCP bug assistance",
    "code_reviewer": "D · Code review",
    "ecommerce": "E · E-commerce",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", env_ignore_empty=True)
    auth_mode: Literal["local", "google"] = "local"
    local_access_token: SecretStr = SecretStr("")
    google_client_id: str = ""
    allowed_google_subjects: str = ""
    google_api_key: SecretStr = SecretStr("")
    gemini_model: str = ""
    # Vertex AI bills the Cloud project, where Free Trial credits apply; the Gemini
    # Developer API key bills a separate pipeline that those credits do not cover.
    google_genai_use_vertexai: bool = False
    google_cloud_project: str = ""
    # Gemini 3 models are served from the global endpoint on Vertex AI; regional
    # endpoints such as us-central1 return 404 NOT_FOUND for them.
    google_cloud_location: str = "global"
    # Part B. Blank gemini_cli_path falls back to the pinned local install, then PATH.
    gemini_cli_path: str = ""
    gemini_workspace: str = ""
    # Part C. The default URL is the official remote GitHub MCP server's issues
    # toolset in read-only mode; see agents/bug_assistant/README.md.
    github_token: SecretStr = SecretStr("")
    github_allowed_repositories: str = ""
    github_mcp_url: str = "https://api.githubcopilot.com/mcp/x/issues/readonly"
    session_database_url: SecretStr = SecretStr("")

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        token = self.local_access_token.get_secret_value()
        if token and len(token) < 32:
            raise ValueError("LOCAL_ACCESS_TOKEN requires at least 32 characters")
        return self

    @property
    def database_url(self) -> str:
        configured = self.session_database_url.get_secret_value()
        if configured:
            return configured
        directory = ROOT / ".local"
        directory.mkdir(mode=0o700, exist_ok=True)
        return f"sqlite+aiosqlite:///{directory / 'sessions.db'}"

    def provider_missing(self) -> list[str]:
        """Settings the selected Gemini backend needs. Presence is not entitlement.

        A pure configuration report for readiness messaging. Actual resolution,
        including credential discovery, lives in agent_core.provider.
        """
        required: tuple[tuple[str, str], ...]
        if self.google_genai_use_vertexai:
            required = (
                ("GOOGLE_CLOUD_PROJECT", self.google_cloud_project),
                ("GOOGLE_CLOUD_LOCATION", self.google_cloud_location),
                ("GEMINI_MODEL", self.gemini_model),
            )
        else:
            required = (
                ("GOOGLE_API_KEY", self.google_api_key.get_secret_value()),
                ("GEMINI_MODEL", self.gemini_model),
            )
        return [name for name, value in required if not value]

    def auth_missing(self) -> list[str]:
        if self.auth_mode == "local":
            return [] if self.local_access_token.get_secret_value() else ["LOCAL_ACCESS_TOKEN"]
        return [
            name
            for name, value in (
                ("GOOGLE_CLIENT_ID", self.google_client_id),
                ("ALLOWED_GOOGLE_SUBJECTS", self.allowed_google_subjects),
            )
            if not value
        ]
