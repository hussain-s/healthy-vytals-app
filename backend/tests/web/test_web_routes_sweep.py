"""Cross-cutting web route sweep (DESIGN §10 web testing).

Asserts consistent behavior across the server-rendered surface without a JS
engine: public pages render, protected pages redirect when anonymous, the landing
nav reflects logged-out state, and role-appropriate dashboards render. Individual
feature behaviors are covered in the per-feature web tests; this is the safety net
that catches a route regressing wholesale.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

PW = "longenough1"

# Protected pages that must bounce an anonymous visitor to /login (303).
PROTECTED_GET = [
    "/dashboard",
    "/appointments/book",
    "/appointments/mine",
    "/clinical/history",
    "/clinical/prescriptions",
]

# Public pages that render for anyone.
PUBLIC_GET = ["/", "/login", "/register"]


@pytest.mark.parametrize("path", PUBLIC_GET)
def test_public_pages_render(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")


@pytest.mark.parametrize("path", PROTECTED_GET)
def test_protected_pages_redirect_when_anonymous(client: TestClient, path: str) -> None:
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_landing_nav_shows_login_when_anonymous(client: TestClient) -> None:
    body = client.get("/").text
    assert "/login" in body and "/register" in body


def test_landing_after_login_flows_to_dashboard(client: TestClient) -> None:
    # A registered patient reaches their dashboard, which shows a logout control.
    client.post("/register", data={"email": "pat@example.com", "password": PW})
    dash = client.get("/dashboard")
    assert dash.status_code == 200
    assert "Log out" in dash.text


def test_unknown_page_is_404(client: TestClient) -> None:
    assert client.get("/no-such-page").status_code == 404


def test_static_assets_served(client: TestClient) -> None:
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/static/htmx.min.js").status_code == 200
