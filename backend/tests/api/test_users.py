"""API tests for admin user provisioning (app.api.v1.users).

Exercises the require_roles(ADMIN) gate end to end: an admin can provision staff,
a patient cannot (403), and an unauthenticated caller is 401. An admin is created
directly in the test DB (staff are not self-service), then logged in for a token.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.models.user import User


@pytest.fixture
def admin_token(client: TestClient, db_sessionmaker: sessionmaker[Session]) -> str:
    """Create an admin directly in the DB and return its access token."""
    with db_sessionmaker() as s:
        s.add(
            User(
                email="admin@example.com",
                password_hash=hash_password("longenough1"),
                role=Role.ADMIN,
            )
        )
        s.commit()
    resp = client.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": "longenough1"}
    )
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_can_provision_doctor(client: TestClient, admin_token: str) -> None:
    resp = client.post(
        "/api/v1/users",
        headers=_auth(admin_token),
        json={"email": "doc@example.com", "password": "longenough1", "role": "doctor"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "doctor"
    assert "password_hash" not in body


def test_provision_requires_authentication(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/users",
        json={"email": "doc@example.com", "password": "longenough1", "role": "doctor"},
    )
    assert resp.status_code == 401


def test_patient_cannot_provision_staff(client: TestClient) -> None:
    """A non-admin (patient) is forbidden from the provisioning endpoint (A5)."""
    client.post(
        "/api/v1/auth/register", json={"email": "pat@example.com", "password": "longenough1"}
    )
    login = client.post(
        "/api/v1/auth/login", json={"email": "pat@example.com", "password": "longenough1"}
    )
    patient_token = login.json()["access_token"]

    resp = client.post(
        "/api/v1/users",
        headers=_auth(patient_token),
        json={"email": "doc@example.com", "password": "longenough1", "role": "doctor"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "permission_denied"


def test_provision_patient_role_is_rejected(client: TestClient, admin_token: str) -> None:
    resp = client.post(
        "/api/v1/users",
        headers=_auth(admin_token),
        json={"email": "x@example.com", "password": "longenough1", "role": "patient"},
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "staff_role_required"
