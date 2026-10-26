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
