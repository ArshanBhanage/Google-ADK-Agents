import runpy
import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from google.adk.agents import Agent, ParallelAgent, SequentialAgent
from google.adk.runners import Runner
from pydantic import SecretStr, ValidationError

from api.main import create_app
from packages.agent_core.config import ROOT, Settings


def configured(tmp_path: Path, token: str | None = None) -> Settings:
    return Settings(
        _env_file=None,
        local_access_token=SecretStr(token or secrets.token_urlsafe(32)),
        session_database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}"),
    )


def bearer(config: Settings) -> dict[str, str]:
    return {"Authorization": "Bearer " + config.local_access_token.get_secret_value()}


def test_auth_required_and_no_secret_response(tmp_path: Path) -> None:
    config = configured(tmp_path)
    with TestClient(create_app(config)) as client:
        assert client.get("/api/health").status_code == 200
        assert client.post("/api/sessions", json={"agent": "lead_research"}).status_code == 401
        assert (
            client.post(
                "/api/sessions",
                json={"agent": "lead_research"},
                headers={"Authorization": "Bearer invalid"},
            ).status_code
            == 401
        )
        response = client.get("/api/readiness")
        assert response.status_code == 503
        assert config.local_access_token.get_secret_value() not in response.text
        assert response.headers["X-Request-ID"]
        assert response.headers["Cache-Control"] == "no-store"


def test_unconfigured_auth_fails_closed(tmp_path: Path) -> None:
    config = configured(tmp_path).model_copy(update={"local_access_token": SecretStr("")})
    with TestClient(create_app(config)) as client:
        response = client.post("/api/sessions", json={"agent": "lead_research"})
        assert response.status_code == 503
        assert response.json()["detail"]["missing"] == ["LOCAL_ACCESS_TOKEN"]


def test_session_persists_across_restart_and_enforces_owner(tmp_path: Path) -> None:
    first = configured(tmp_path)
    with TestClient(create_app(first)) as client:
        response = client.post(
            "/api/sessions", json={"agent": "lead_research"}, headers=bearer(first)
        )
        assert response.status_code == 201
        path = "/api/sessions/lead_research/" + response.json()["id"]
    second = configured(tmp_path)
    with TestClient(create_app(second)) as client:
        assert client.get(path, headers=bearer(second)).status_code == 404
        assert client.delete(path, headers=bearer(second)).status_code == 404
    with TestClient(create_app(first)) as client:
        assert client.get(path, headers=bearer(first)).status_code == 200
        assert (
            client.get(
                path.replace("lead_research", "ecommerce"), headers=bearer(first)
            ).status_code
            == 404
        )
        assert client.delete(path, headers=bearer(first)).status_code == 204
        assert client.get(path, headers=bearer(first)).status_code == 404


def test_identity_cannot_be_supplied_by_client(tmp_path: Path) -> None:
    config = configured(tmp_path)
    with TestClient(create_app(config)) as client:
        assert (
            client.post(
                "/api/sessions",
                json={"agent": "lead_research", "user_id": "someone-else"},
                headers=bearer(config),
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/sessions", json={"agent": "../../etc/passwd"}, headers=bearer(config)
            ).status_code
            == 422
        )


def test_short_access_token_rejected() -> None:
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(_env_file=None, local_access_token=SecretStr("short"))


def test_setup_preserves_values_and_rejects_symlinks(tmp_path: Path) -> None:
    setup = runpy.run_path(str(ROOT / "scripts/setup-env"))["setup"]
    (tmp_path / "web").mkdir()
    (tmp_path / "agents").mkdir()
    (tmp_path / ".env.example").write_text("VALUE=\n")
    (tmp_path / "web/.env.example").write_text("# no client secrets\n")
    assert setup(tmp_path) == [".env: VALUE"]
    secret = secrets.token_urlsafe(32)
    (tmp_path / ".env").write_text("VALUE=" + secret)
    assert setup(tmp_path) == []
    assert (tmp_path / ".env").read_text() == "VALUE=" + secret
    assert (tmp_path / ".env").stat().st_mode & 0o777 == 0o600
    (tmp_path / ".env").unlink()
    (tmp_path / ".env").symlink_to(tmp_path / ".env.example")
    with pytest.raises(ValueError, match="symlink"):
        setup(tmp_path)


def test_installed_adk_workflow_apis() -> None:
    pipeline = SequentialAgent(
        name="foundation_import_check",
        sub_agents=[
            ParallelAgent(name="parallel_api_check", sub_agents=[Agent(name="agent_api_check")])
        ],
    )
    assert pipeline.sub_agents[0].name == "parallel_api_check"
    assert callable(Runner.run_async)
