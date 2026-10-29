"""Part C settings, scoped to this component.

The deliverable contract puts component-specific credentials in the component's own
`.env`, so a GitHub token belongs in `agents/bug_assistant/.env` rather than the shared
root file. Both are read, with the component file taking precedence, so shared values
such as the model still come from root while the token stays local to Part C.
"""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

COMPONENT = Path(__file__).resolve().parent
ROOT = COMPONENT.parents[1]


class BugSettings(BaseSettings):
    model_config = SettingsConfigDict(
        # Later files win, so the component file overrides root.
        env_file=(ROOT / ".env", COMPONENT / ".env"),
        extra="ignore",
        env_ignore_empty=True,
    )
    github_token: SecretStr = SecretStr("")
    github_allowed_repositories: str = ""
    github_mcp_url: str = "https://api.githubcopilot.com/mcp/x/issues/readonly"
    # Writes are a separate gate: a separate opt-in and a separately scoped token.
    github_write_enabled: bool = False
    github_write_token: SecretStr = SecretStr("")
    github_write_mcp_url: str = "https://api.githubcopilot.com/mcp/x/issues"

    def write_missing(self) -> list[str]:
        if not self.github_write_enabled:
            return ["GITHUB_WRITE_ENABLED"]
        return [] if self.github_write_token.get_secret_value() else ["GITHUB_WRITE_TOKEN"]
