"""API tests for the auth endpoints (app.api.v1.auth).

Uses the shared `client` fixture (temp DB, overridden get_session). This slice
covers registration; login/refresh endpoints are tested when they land.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _register_and_login(client: TestClient, email: str = "pat@example.com") -> dict:
    client.post("/api/v1/auth/register", json={"email": email, "password": "longenough1"})
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "longenough1"})
    assert resp.status_code == 200
    return resp.json()


def test_register_returns_201_and_safe_user(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "pat@example.com", "password": "longenough1"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "pat@example.com"
    assert body["role"] == "patient"
    assert body["is_active"] is True
    # The response must never carry the credential hash.
    assert "password_hash" not in body


def test_register_duplicate_email_returns_409(client: TestClient) -> None:
    payload = {"email": "dup@example.com", "password": "longenough1"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201

    conflict = client.post("/api/v1/auth/register", json=payload)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "email_already_registered"


def test_register_rejects_invalid_payload(client: TestClient) -> None:
    """Bad email / short password are rejected at the boundary with 422."""
    bad_email = client.post(
        "/api/v1/auth/register", json={"email": "nope", "password": "longenough1"}
    )
    assert bad_email.status_code == 422
    assert bad_email.json()["code"] == "request_validation_error"

    short_pw = client.post(
        "/api/v1/auth/register", json={"email": "a@b.com", "password": "short"}
    )
    assert short_pw.status_code == 422


def test_login_returns_token_pair(client: TestClient) -> None:
    tokens = _register_and_login(client)
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"] and tokens["refresh_token"]


def test_login_wrong_password_returns_401(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register", json={"email": "pat@example.com", "password": "longenough1"}
    )
    resp = client.post(
        "/api/v1/auth/login", json={"email": "pat@example.com", "password": "wrongpass1"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "invalid_credentials"


def test_me_requires_authentication(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_me_returns_current_user_with_bearer(client: TestClient) -> None:
    tokens = _register_and_login(client)
    resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "pat@example.com"


def test_refresh_returns_new_pair(client: TestClient) -> None:
    tokens = _register_and_login(client)
    resp = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_refresh_rejects_access_token(client: TestClient) -> None:
    tokens = _register_and_login(client)
    resp = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )
    assert resp.status_code == 401
