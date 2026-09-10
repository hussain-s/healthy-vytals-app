"""API tests for admin patient search (NEW feature)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.models.user import User

PW = "longenough1"


@pytest.fixture
def world(db_sessionmaker: sessionmaker[Session]) -> None:
    with db_sessionmaker() as s:
        s.add_all([
            User(email="admin@example.com", password_hash=hash_password(PW), role=Role.ADMIN),
            User(email="alice@example.com", password_hash=hash_password(PW), role=Role.PATIENT),
            User(email="bob@example.com", password_hash=hash_password(PW), role=Role.PATIENT),
        ])
        s.commit()


def _token(client: TestClient, email: str) -> str:
    return client.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()[
        "access_token"
    ]


def test_admin_can_search_patients_by_email(client: TestClient, world: None) -> None:
    admin = _token(client, "admin@example.com")
    resp = client.get("/api/v1/patients/search", params={"q": "alice"},
                      headers={"Authorization": f"Bearer {admin}"})
    assert resp.status_code == 200
    emails = [u["email"] for u in resp.json()]
    assert emails == ["alice@example.com"]


def test_non_admin_cannot_search(client: TestClient, world: None) -> None:
    pat = _token(client, "alice@example.com")
    resp = client.get("/api/v1/patients/search", params={"q": "bob"},
                      headers={"Authorization": f"Bearer {pat}"})
    assert resp.status_code == 403
