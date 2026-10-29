from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

COMPONENT = Path(__file__).resolve().parent
ROOT = COMPONENT.parents[1]


class CommerceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT / ".env", COMPONENT / ".env"),
        env_ignore_empty=True,
        populate_by_name=True,
        extra="ignore",
        hide_input_in_errors=True,
    )
    google_genai_use_vertexai: bool = True
    google_cloud_project: str = ""
    google_cloud_location: str = "global"
    gemini_model: str = "gemini-3.6-flash"
    database_url: SecretStr = Field(
        default=SecretStr(""), validation_alias=AliasChoices("DATABASE_URL", "ALLOYDB_DATABASE_URL")
    )
    migration_database_url: SecretStr = SecretStr("")
    toolbox_url: str = ""
    toolbox_audience: str = ""
    shopify_store_domain: str = ""
    shopify_storefront_token: SecretStr = SecretStr("")
    shopify_token_type: Literal["public", "private"] = "public"
    shopify_api_version: Literal["2026-10"] = "2026-10"
    max_catalog_products: int = Field(default=10000, ge=1, le=100000)
    database_mode: Literal["local_postgres", "alloydb"] = "local_postgres"

    @field_validator("google_genai_use_vertexai")
    @classmethod
    def vertex_required(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Part E requires Vertex AI; Developer API fallback is disabled")
        return value

    @field_validator("shopify_store_domain")
    @classmethod
    def merchant_host(cls, value: str) -> str:
        if not value:
            return value
        import re

        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com", value):
            raise ValueError("Use the authorized merchant's bare myshopify.com hostname")
        return value

    @field_validator("toolbox_url")
    @classmethod
    def toolbox_endpoint(cls, value: str) -> str:
        if not value:
            return value
        url = urlsplit(value)
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("Toolbox URL must not contain credentials, queries or fragments")
        if url.scheme != "https" and not (
            url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost"}
        ):
            raise ValueError("Use HTTPS or a loopback-only local Toolbox endpoint")
        if not url.hostname or not (url.path == "/mcp" or url.path.startswith("/mcp/")):
            raise ValueError("Toolbox 1.x requires an /mcp endpoint")
        return value

    def missing(self) -> list[str]:
        return [
            name
            for name, value in (
                ("GOOGLE_CLOUD_PROJECT", self.google_cloud_project),
                ("GOOGLE_CLOUD_LOCATION", self.google_cloud_location),
                ("GEMINI_MODEL", self.gemini_model),
                ("DATABASE_URL", self.database_url.get_secret_value()),
                ("TOOLBOX_URL", self.toolbox_url),
                ("SHOPIFY_STORE_DOMAIN", self.shopify_store_domain),
                ("SHOPIFY_STOREFRONT_TOKEN", self.shopify_storefront_token.get_secret_value()),
            )
            if not value
        ]
