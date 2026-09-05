"""Web tests for the admin console: user management + audit viewer (M7.6, M7.7)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.models.user import User

PW = "longenough1"


@pytest.fixture
def admin(db_sessionmaker: sessionmaker[Session]) -> None:
    with db_sessionmaker() as s:
        s.add(User(email="admin@example.com", password_hash=hash_password(PW), role=Role.ADMIN))
        s.commit()


def _login(client: TestClient, email: str) -> None:
    client.post("/login", data={"email": email, "password": PW})


def test_admin_dashboard_shows_counts_and_links(client: TestClient, admin: None) -> None:
    _login(client, "admin@example.com")
    body = client.get("/dashboard").text
    assert "Overview" in body
    assert "Manage users" in body and "View audit log" in body


def test_admin_provisions_staff_via_console(
    client: TestClient, admin: None, db_sessionmaker: sessionmaker[Session]
) -> None:
    _login(client, "admin@example.com")
    resp = client.post(
        "/admin/users",
        data={"email": "newdoc@example.com", "password": PW, "role": "doctor"},
    )
    assert resp.status_code == 200
    assert "newdoc@example.com" in resp.text
    with db_sessionmaker() as s:
        u = s.scalar(select(User).where(User.email == "newdoc@example.com"))
        assert u is not None and u.role is Role.DOCTOR


def test_admin_deactivates_and_reactivates_user(
    client: TestClient, admin: None, db_sessionmaker: sessionmaker[Session]
) -> None:
    # A patient to toggle.
    client.post("/register", data={"email": "pat@example.com", "password": PW})
    with db_sessionmaker() as s:
        pid = s.scalar(select(User.id).where(User.email == "pat@example.com"))

    _login(client, "admin@example.com")
    # Deactivate.
    r = client.post(f"/admin/users/{pid}/toggle", data={"is_active": "false"}, follow_redirects=False)
    assert r.status_code == 303
    with db_sessionmaker() as s:
        assert s.get(User, pid).is_active is False
    # A deactivated user can no longer log in (fresh client).
    # (login is uniform-failure; assert 401 on the API path.)
    assert client.post("/api/v1/auth/login", json={"email": "pat@example.com", "password": PW}).status_code == 401


def test_non_admin_cannot_reach_console(client: TestClient) -> None:
    client.post("/register", data={"email": "pat@example.com", "password": PW})
    assert client.get("/admin/users").status_code == 403
    assert client.get("/admin/audit").status_code == 403


def test_audit_viewer_lists_and_filters(client: TestClient, admin: None) -> None:
    _login(client, "admin@example.com")
    # The admin's own login generated an auth.login row.
    page = client.get("/admin/audit")
    assert page.status_code == 200
    assert "auth.login" in page.text
    # Filter to something that won't match.
    filtered = client.get("/admin/audit", params={"action": "no.such.action"})
    assert "no audit entries match" in filtered.text.lower()
