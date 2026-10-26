import asyncio
import hashlib
import secrets
from dataclasses import dataclass

from fastapi import HTTPException
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.id_token import verify_oauth2_token

from packages.agent_core.config import Settings


@dataclass(frozen=True)
class Identity:
    subject: str


async def authenticate(authorization: str | None, settings: Settings) -> Identity:
    if settings.auth_missing():
        raise HTTPException(503, {"code": "BLOCKED_AUTH", "missing": settings.auth_missing()})
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bearer authentication required")
    token = authorization.removeprefix("Bearer ")
    if len(token) > 8192:
        raise HTTPException(401, "Invalid credential")
    if settings.auth_mode == "local":
        expected = settings.local_access_token.get_secret_value()
        if not secrets.compare_digest(token, expected):
            raise HTTPException(401, "Invalid credential")
        return Identity("local:" + hashlib.sha256(token.encode()).hexdigest())
    try:
        claims = await asyncio.to_thread(
            verify_oauth2_token, token, Request(), settings.google_client_id
        )
    except (ValueError, GoogleAuthError) as exc:
        raise HTTPException(401, "Google identity verification failed") from exc
    subject = claims.get("sub")
    allowed = {item.strip() for item in settings.allowed_google_subjects.split(",")}
    if not isinstance(subject, str) or subject not in allowed:
        raise HTTPException(403, "Account is not authorized")
    return Identity("google:" + subject)
