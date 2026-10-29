"""C2 route security tests. No provider or MCP call is made."""

import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from api.main import create_app
from packages.agent_core.config import Settings

TRIAGE_BODY = {
    "owner": "google",
    "repo": "adk-python",
    "description": "Session identity components are not validated before use in paths.",
}
WRITE_BODY = {
    "approval_token": "a" * 32,
    "proposed_issue": {
        "owner": "google",
        "repo": "adk-python",
        "title": "Unvalidated identity components",
        "body": "A body long enough to satisfy the schema constraints.",
    },
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


def bug_session(client: TestClient, token: str) -> str:
    response = client.post("/api/sessions", json={"agent": "bug_assistant"}, headers=bearer(token))
    assert response.status_code == 201
    return str(response.json()["id"])


def test_both_routes_require_authentication(tmp_path: Path, owner_token: str) -> None:
    with TestClient(create_app(configured(tmp_path, owner_token))) as client:
        session = bug_session(client, owner_token)
        for path, body in (
            (f"/api/agents/bug_assistant/{session}/triage", TRIAGE_BODY),
            (f"/api/agents/bug_assistant/{session}/create-issue", WRITE_BODY),
        ):
            for headers in ({}, {"Authorization": "Bearer wrong"}):
                assert client.post(path, json=body, headers=headers).status_code == 401


def test_filing_without_an_approval_in_the_session_is_forbidden(
    tmp_path: Path, owner_token: str
) -> None:
    # The decisive negative case: a valid user, a valid session, a well-formed body,
    # and no approval. Must be 403, not a created issue.
    with TestClient(create_app(configured(tmp_path, owner_token))) as client:
        session = bug_session(client, owner_token)
        response = client.post(
            f"/api/agents/bug_assistant/{session}/create-issue",
            json=WRITE_BODY,
            headers=bearer(owner_token),
        )
        assert response.status_code == 403
        assert "BLOCKED_NO_APPROVAL" in response.json()["detail"]


def test_the_write_route_is_scoped_to_the_owning_identity(tmp_path: Path) -> None:
    owner = secrets.token_urlsafe(32)
    with TestClient(create_app(configured(tmp_path, owner))) as client:
        session = bug_session(client, owner)
    intruder = secrets.token_urlsafe(32)
    with TestClient(create_app(configured(tmp_path, intruder))) as client:
        assert (
            client.post(
                f"/api/agents/bug_assistant/{session}/create-issue",
                json=WRITE_BODY,
                headers=bearer(intruder),
            ).status_code
            == 404
        )


def test_a_session_from_another_agent_cannot_be_used(tmp_path: Path, owner_token: str) -> None:
    with TestClient(create_app(configured(tmp_path, owner_token))) as client:
        response = client.post(
            "/api/sessions", json={"agent": "lead_research"}, headers=bearer(owner_token)
        )
        other = str(response.json()["id"])
        assert (
            client.post(
                f"/api/agents/bug_assistant/{other}/create-issue",
                json=WRITE_BODY,
                headers=bearer(owner_token),
            ).status_code
            == 404
        )


@pytest.mark.parametrize(
    "bad",
    [
        {**TRIAGE_BODY, "description": "too short"},
        {**TRIAGE_BODY, "owner": "has space"},
        {**TRIAGE_BODY, "repo": "bad/slash"},
        {**TRIAGE_BODY, "extra": "field"},
        {"owner": "google"},
    ],
)
def test_invalid_triage_requests_are_rejected_before_any_mcp_call(
    tmp_path: Path, owner_token: str, bad: dict[str, object]
) -> None:
    with TestClient(create_app(configured(tmp_path, owner_token))) as client:
        session = bug_session(client, owner_token)
        assert (
            client.post(
                f"/api/agents/bug_assistant/{session}/triage", json=bad, headers=bearer(owner_token)
            ).status_code
            == 422
        )


@pytest.mark.parametrize(
    "bad",
    [
        {"approval_token": "short", "proposed_issue": WRITE_BODY["proposed_issue"]},
        {"proposed_issue": WRITE_BODY["proposed_issue"]},
        {"approval_token": "a" * 32},
        {**WRITE_BODY, "extra": "field"},
        {
            "approval_token": "a" * 32,
            "proposed_issue": {**WRITE_BODY["proposed_issue"], "owner": "has space"},  # type: ignore[dict-item]
        },
    ],
)
def test_malformed_write_requests_are_rejected_by_the_schema(
    tmp_path: Path, owner_token: str, bad: dict[str, object]
) -> None:
    with TestClient(create_app(configured(tmp_path, owner_token))) as client:
        session = bug_session(client, owner_token)
        assert (
            client.post(
                f"/api/agents/bug_assistant/{session}/create-issue",
                json=bad,
                headers=bearer(owner_token),
            ).status_code
            == 422
        )
