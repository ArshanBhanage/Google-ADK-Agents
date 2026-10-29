"""Part D settings, scoped to this component.

Review is read-only, so the token needs read access to Pull Requests and Contents on
the allowlisted repositories and nothing else. It lives in this component's `.env`,
not the shared root file.
"""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

COMPONENT = Path(__file__).resolve().parent
ROOT = COMPONENT.parents[1]


class ReviewSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", COMPONENT / ".env"),
        extra="ignore",
        env_ignore_empty=True,
    )
    github_token: SecretStr = SecretStr("")
    github_allowed_repositories: str = ""
    github_api_url: str = "https://api.github.com"
    # A pull request larger than this is reported as too large rather than truncated
    # into a review that silently ignored most of the change.
    max_changed_files: int = 60
    max_patch_bytes: int = 400_000
