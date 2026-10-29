"""Real, empty PostgreSQL + MCP integration; no business fixtures or cloud resources."""

import asyncio
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
from pathlib import Path

import psycopg
from psycopg import sql

from .config import COMPONENT, CommerceSettings
from .database import migrate
from .mcp_client import probe_toolbox

IMAGE = "postgres@sha256:b8faeff7712663c2773a190181e1246e37e364b887611c04658c28b44e2408fe"


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.DEVNULL).strip()


async def check() -> dict[str, object]:
    binary = os.environ.get("TOOLBOX_BINARY", "/private/tmp/ecommerce-toolbox")
    name = "ecommerce-check-" + secrets.token_hex(6)
    password = secrets.token_urlsafe(32)
    process = None
    started = False
    with tempfile.TemporaryDirectory(prefix="ecommerce-check-") as directory:
        envfile = Path(directory) / "postgres.env"
        envfile.write_text(f"POSTGRES_PASSWORD={password}\nPOSTGRES_DB=commerce\n")
        envfile.chmod(0o600)
        try:
            docker(
                "run",
                "--rm",
                "-d",
                "--name",
                name,
                "--env-file",
                str(envfile),
                "-p",
                "127.0.0.1::5432",
                IMAGE,
            )
            started = True
            port = docker("port", name, "5432/tcp").rsplit(":", 1)[1]
            for _ in range(60):
                ready = subprocess.run(
                    ["docker", "exec", name, "pg_isready", "-U", "postgres"], capture_output=True
                )
                if ready.returncode == 0:
                    break
                await asyncio.sleep(0.5)
            dsn = f"postgresql://postgres:{password}@127.0.0.1:{port}/commerce"
            settings = CommerceSettings(
                _env_file=None, database_url=dsn, database_mode="local_postgres"
            )
            await migrate(settings)
            await migrate(settings)
            with psycopg.connect(dsn, autocommit=True) as db:
                db.execute((COMPONENT / "infra/002_roles.sql").read_text())
                db.execute(
                    sql.SQL("CREATE ROLE catalog LOGIN PASSWORD {}").format(sql.Literal(password))
                )
                db.execute("GRANT commerce_catalog_reader TO catalog")
                count_row = db.execute("SELECT count(*) FROM commerce.products").fetchone()
                version_row = db.execute("SHOW server_version").fetchone()
                assert count_row is not None and version_row is not None
                count, version = count_row[0], version_row[0]
            denied = []
            with psycopg.connect(dsn.replace("postgres:", "catalog:", 1), autocommit=True) as db:
                for query in ["SELECT * FROM commerce.users", "DELETE FROM commerce.products"]:
                    try:
                        db.execute(query)
                    except psycopg.errors.InsufficientPrivilege:
                        denied.append(True)
                    else:
                        raise AssertionError("Catalog role has excessive permissions")
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                tool_port = sock.getsockname()[1]
            env = dict(
                os.environ,
                DB_HOST="127.0.0.1",
                DB_PORT=port,
                DB_NAME="commerce",
                DB_USER="catalog",
                DB_PASSWORD=password,
                SHOPIFY_STORE_DOMAIN="",
            )
            configs = ",".join(
                str(COMPONENT / "infra" / f) for f in ("toolbox-local.yaml", "catalog-tools.yaml")
            )
            with (Path(directory) / "toolbox.log").open("w") as log:
                process = subprocess.Popen(
                    [
                        binary,
                        "--configs",
                        configs,
                        "--port",
                        str(tool_port),
                        "--address",
                        "127.0.0.1",
                        "--disable-version-check",
                        "--allowed-hosts",
                        "127.0.0.1,localhost",
                        "--allowed-origins",
                        "http://127.0.0.1:8085,http://localhost:8085",
                    ],
                    env=env,
                    stdout=log,
                    stderr=log,
                )
                for _ in range(60):
                    if process.poll() is not None:
                        raise RuntimeError("Toolbox failed to start")
                    try:
                        with socket.create_connection(("127.0.0.1", tool_port), timeout=0.2):
                            break
                    except OSError:
                        await asyncio.sleep(0.25)
                settings.toolbox_url = f"http://127.0.0.1:{tool_port}/mcp/catalog"
                result = await probe_toolbox(settings)
                return {
                    **result,
                    "postgres_version": version,
                    "product_rows": count,
                    "migrations_idempotent": True,
                    "forbidden_queries_denied": len(denied),
                    "merchant_gate": "BLOCKED: no authorized Shopify store or AlloyDB",
                    "checked_at_unix": int(time.time()),
                    "postgres_image": IMAGE,
                }
        finally:
            if process is not None:
                process.terminate()
                process.wait(timeout=10)
            if started:
                docker("rm", "-f", name)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(check()), indent=2))
