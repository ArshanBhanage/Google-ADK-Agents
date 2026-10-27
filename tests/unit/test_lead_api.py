"""Security and contract tests for the A2 endpoints. No provider call is made."""

import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from api.main import create_app
from packages.agent_core.config import Settings

CRITERIA = {
    "industry": "industrial CNC machining services",
    "region": "Ohio, United States",
    "buyer_profile": "independent machine shops publishing capability pages",
    "quantity": 2,
    "exclusions": [],
}


def configured(tmp_path: Path, token: str) -> Settings:
    return Settings(
        _env_file=None,
        local_access_token=SecretStr(token),
        session_database_url=SecretStr(f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}"),
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


@pytest.fixture
def owner_token() -> str:
    return secrets.token_urlsafe(32)


def new_session(client: TestClient, token: str) -> str:
    response = client.post("/api/sessions", json={"agent": "lead_research"}, headers=bearer(token))
    assert response.status_code == 201
    return str(response.json()["id"])


def test_research_and_export_require_authentication(tmp_path: Path, owner_token: str) -> None:
    config = configured(tmp_path, owner_token)
    with TestClient(create_app(config)) as client:
        session = new_session(client, owner_token)
        research = f"/api/agents/lead_research/{session}/research"
        export = f"/api/agents/lead_research/{session}/export.csv"
        for headers in ({}, {"Authorization": "Bearer wrong"}):
            assert client.post(research, json=CRITERIA, headers=headers).status_code == 401
            assert client.get(export, headers=headers).status_code == 401


def test_export_before_any_research_is_a_conflict_not_an_empty_file(
    tmp_path: Path, owner_token: str
) -> None:
    config = configured(tmp_path, owner_token)
    with TestClient(create_app(config)) as client:
        session = new_session(client, owner_token)
        response = client.get(
            f"/api/agents/lead_research/{session}/export.csv", headers=bearer(owner_token)
        )
        assert response.status_code == 409


def test_another_identity_cannot_reach_someone_elses_session(tmp_path: Path) -> None:
    owner = secrets.token_urlsafe(32)
    with TestClient(create_app(configured(tmp_path, owner))) as client:
        session = new_session(client, owner)
    # A different valid credential resolves to a different subject on the same database.
    intruder = secrets.token_urlsafe(32)
    with TestClient(create_app(configured(tmp_path, intruder))) as client:
        assert (
            client.get(
                f"/api/agents/lead_research/{session}/export.csv", headers=bearer(intruder)
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/agents/lead_research/{session}/research",
                json=CRITERIA,
                headers=bearer(intruder),
            ).status_code
            == 404
        )


def test_unknown_session_is_rejected_before_any_billable_work(
    tmp_path: Path, owner_token: str
) -> None:
    config = configured(tmp_path, owner_token)
    with TestClient(create_app(config)) as client:
        missing = "11111111-2222-3333-4444-555555555555"
        assert (
            client.post(
                f"/api/agents/lead_research/{missing}/research",
                json=CRITERIA,
                headers=bearer(owner_token),
            ).status_code
            == 404
        )


@pytest.mark.parametrize(
    "identifier", ["..%2F..%2Fetc%2Fpasswd", "not-a-uuid", "1' OR '1'='1", "../../etc/passwd"]
)
def test_malformed_session_identifier_is_rejected(
    tmp_path: Path, owner_token: str, identifier: str
) -> None:
    config = configured(tmp_path, owner_token)
    with TestClient(create_app(config)) as client:
        # Either routing refuses the path or the UUID type refuses the value. Never a
        # 200, and never a 5xx that would imply the request reached the pipeline.
        assert client.post(
            f"/api/agents/lead_research/{identifier}/research",
            json=CRITERIA,
            headers=bearer(owner_token),
        ).status_code in {404, 422}


@pytest.mark.parametrize(
    "bad",
    [
        {**CRITERIA, "quantity": 0},
        {**CRITERIA, "quantity": 99},
        {**CRITERIA, "industry": "x"},
        {**CRITERIA, "unexpected": "field"},
        {"industry": "software"},
    ],
)
def test_invalid_criteria_are_rejected_before_any_billable_work(
    tmp_path: Path, owner_token: str, bad: dict[str, object]
) -> None:
    config = configured(tmp_path, owner_token)
    with TestClient(create_app(config)) as client:
        session = new_session(client, owner_token)
        response = client.post(
            f"/api/agents/lead_research/{session}/research",
            json=bad,
            headers=bearer(owner_token),
        )
        assert response.status_code == 422
