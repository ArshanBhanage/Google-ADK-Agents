"""Locally issued per-user bearer credentials; hashes only in PostgreSQL."""

import argparse
import asyncio
import hashlib
import secrets
import uuid
from pathlib import Path

from fastapi import HTTPException
from psycopg import AsyncConnection

from .config import COMPONENT, CommerceSettings


async def authenticate(token: str | None, settings: CommerceSettings) -> str:
    if not token or not token.startswith("Bearer ") or len(token) > 512:
        raise HTTPException(401, "Authentication required")
    digest = hashlib.sha256(token[7:].encode()).hexdigest()
    async with await AsyncConnection.connect(settings.database_url.get_secret_value()) as db:
        row = await (
            await db.execute(
                "SELECT subject FROM commerce.access_tokens WHERE token_hash=%s AND NOT revoked",
                (digest,),
            )
        ).fetchone()
    if not row:
        raise HTTPException(401, "Invalid credential")
    return str(row[0])


async def issue(path: Path) -> None:
    token, subject = secrets.token_urlsafe(48), "local:" + str(uuid.uuid4())
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Exclusive create prevents accidentally replacing an existing user's credential.
    with path.open("x") as output:
        path.chmod(0o600)
        async with await AsyncConnection.connect(
            CommerceSettings().database_url.get_secret_value()
        ) as db:
            await db.execute("INSERT INTO commerce.users(subject) VALUES (%s)", (subject,))
            await db.execute(
                "INSERT INTO commerce.access_tokens(token_hash,subject) VALUES (%s,%s)",
                (hashlib.sha256(token.encode()).hexdigest(), subject),
            )
        output.write(token)
    print("Created a local user credential in the requested private file.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, choices=["owner", "isolation-test"])
    asyncio.run(issue(COMPONENT / ".local" / (parser.parse_args().name + ".token")))
