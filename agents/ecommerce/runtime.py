"""Local persistent database setup and loopback-only MCP server launcher."""

import argparse
import asyncio
import os
import secrets
import subprocess
from pathlib import Path

from dotenv import dotenv_values, set_key
from psycopg import AsyncConnection, sql

from .config import COMPONENT, CommerceSettings
from .database import migrate

LOCAL = COMPONENT / ".local"


async def setup() -> None:
    LOCAL.mkdir(mode=0o700, exist_ok=True)
    secret_file = LOCAL / "postgres.env"
    if not secret_file.exists():
        secret_file.write_text("POSTGRES_PASSWORD=" + secrets.token_urlsafe(32) + "\n")
        secret_file.chmod(0o600)
    password = dotenv_values(secret_file)["POSTGRES_PASSWORD"]
    subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            "adk-ecommerce",
            "--env-file",
            str(secret_file),
            "-f",
            str(COMPONENT / "compose.yaml"),
            "up",
            "-d",
            "--wait",
        ],
        check=True,
    )
    env_path = COMPONENT / ".env"
    dsn = f"postgresql://postgres:{password}@127.0.0.1:55432/commerce"
    set_key(env_path, "MIGRATION_DATABASE_URL", dsn)
    set_key(env_path, "DATABASE_MODE", "local_postgres")
    set_key(env_path, "TOOLBOX_URL", "http://127.0.0.1:55000/mcp/catalog")
    env_path.chmod(0o600)
    settings = CommerceSettings()
    await migrate(settings)
    reader_file = LOCAL / "reader.env"
    if not reader_file.exists():
        reader_file.write_text("DB_PASSWORD=" + secrets.token_urlsafe(32) + "\n")
        reader_file.chmod(0o600)
    reader_password = dotenv_values(reader_file)["DB_PASSWORD"]
    async with await AsyncConnection.connect(dsn) as db:
        await db.execute((COMPONENT / "infra/002_roles.sql").read_text())
        await db.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='catalog') "
            "THEN CREATE ROLE catalog LOGIN; END IF; END $$"
        )
        await db.execute(
            sql.SQL("ALTER ROLE catalog PASSWORD {}").format(sql.Literal(reader_password))
        )
        await db.execute("GRANT commerce_catalog_reader TO catalog")
    app_file = LOCAL / "app.env"
    if not app_file.exists():
        app_file.write_text("DB_PASSWORD=" + secrets.token_urlsafe(32) + "\n")
        app_file.chmod(0o600)
    app_password = dotenv_values(app_file)["DB_PASSWORD"]
    async with await AsyncConnection.connect(dsn) as db:
        await db.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='commerce_app') "
            "THEN CREATE ROLE commerce_app LOGIN; END IF; END $$"
        )
        await db.execute(
            sql.SQL("ALTER ROLE commerce_app PASSWORD {}").format(sql.Literal(app_password))
        )
        await db.execute("GRANT USAGE ON SCHEMA commerce TO commerce_app")
        await db.execute(
            "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA commerce TO commerce_app"
        )
        await db.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA commerce TO commerce_app")
        await db.execute("CREATE SCHEMA IF NOT EXISTS adk_sessions AUTHORIZATION commerce_app")
        await db.execute("ALTER ROLE commerce_app SET search_path TO adk_sessions")
    set_key(
        env_path,
        "DATABASE_URL",
        f"postgresql://commerce_app:{app_password}@127.0.0.1:55432/commerce",
    )
    print("Local PostgreSQL ready; credentials stored only in ignored local files.")


def toolbox() -> None:
    settings = CommerceSettings()  # validates operator-controlled SQL substitution
    if not settings.shopify_store_domain:
        raise ValueError("Configure the authorized Shopify merchant first")
    binary = os.environ.get("TOOLBOX_BINARY", "/private/tmp/ecommerce-toolbox")
    if not Path(binary).is_file():
        raise ValueError("Set TOOLBOX_BINARY to the official v1.15.0 executable")
    env = dict(
        os.environ,
        DB_HOST="127.0.0.1",
        DB_PORT="55432",
        DB_NAME="commerce",
        DB_USER="catalog",
        DB_PASSWORD=dotenv_values(LOCAL / "reader.env")["DB_PASSWORD"] or "",
        SHOPIFY_STORE_DOMAIN=settings.shopify_store_domain,
    )
    configs = ",".join(
        str(COMPONENT / "infra" / f) for f in ("toolbox-local.yaml", "catalog-tools.yaml")
    )
    os.execve(
        binary,
        [
            binary,
            "--configs",
            configs,
            "--address",
            "127.0.0.1",
            "--port",
            "55000",
            "--disable-version-check",
            "--allowed-hosts",
            "127.0.0.1,localhost",
            "--allowed-origins",
            "http://127.0.0.1:8085,http://localhost:8085",
        ],
        env,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["setup", "toolbox"])
    if parser.parse_args().command == "setup":
        asyncio.run(setup())
    else:
        toolbox()
