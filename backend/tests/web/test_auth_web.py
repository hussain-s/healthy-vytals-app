"""Web-layer tests for cookie-session auth and role dashboards.

Tests the server-rendered HTML flow via the shared `client` fixture (temp DB,
overridden get_session): register/login set the cookie, protected pages redirect
when anonymous, each role lands on its own dashboard, and logout clears the
session. No JS engine needed — all logic is server-side.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.deps import SESSION_COOKIE_NAME
from app.core.roles import Role
from app.core.security import hash_password
from app.models.user import User

PW = "longenough1"


def test_login_page_renders(client: TestClient) -> None:
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "Log in" in resp.text


def test_dashboard_redirects_when_anonymous(client: TestClient) -> None:
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_register_then_dashboard_as_patient(client: TestClient) -> None:
    # Register via the web form; should set cookie and redirect to /dashboard.
    resp = client.post(
        "/register",
        data={"email": "pat@example.com", "password": PW},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/dashboard"
    assert SESSION_COOKIE_NAME in resp.cookies

    # The client stored the cookie; the dashboard now renders the patient view.
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert "patient" in dash.text.lower()


def test_login_bad_credentials_rerenders_with_error(client: TestClient) -> None:
    resp = client.post(
        "/login",
        data={"email": "nobody@example.com", "password": PW},
        follow_redirects=False,
    )
    assert resp.status_code == 401
    assert "Incorrect email or password" in resp.text


@pytest.fixture
def make_user(db_sessionmaker: sessionmaker[Session]):
    def _make(email: str, role: Role) -> None:
        with db_sessionmaker() as s:
            s.add(User(email=email, password_hash=hash_password(PW), role=role))
            s.commit()

    return _make


@pytest.mark.parametrize(
    "role,marker",
    [
        (Role.DOCTOR, "Doctor dashboard"),
        (Role.NURSE, "Nurse dashboard"),
        (Role.ADMIN, "Admin dashboard"),
    ],
)
def test_each_role_lands_on_its_dashboard(
    client: TestClient, make_user, role: Role, marker: str
) -> None:
    make_user(f"{role.value}@example.com", role)
    client.post("/login", data={"email": f"{role.value}@example.com", "password": PW})
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert marker in dash.text


def test_logout_clears_session(client: TestClient) -> None:
    client.post("/register", data={"email": "pat@example.com", "password": PW})
    assert client.get("/dashboard").status_code == 200  # logged in

    client.post("/logout", follow_redirects=False)
    # After logout the protected page redirects again.
    assert client.get("/dashboard", follow_redirects=False).status_code == 303
