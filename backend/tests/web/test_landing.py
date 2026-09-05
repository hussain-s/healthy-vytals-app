"""Tests for the web-layer bootstrap (app.web): landing page + HTMX partial.

We test the server-rendered output over HTTP (no JS engine needed — all logic
lives on the server). This proves the Jinja2 + HTMX wiring: the landing page
renders with the HTMX script and an hx-get button, the status partial returns a
bare fragment, and static assets (CSS, vendored HTMX) are served.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())


def test_landing_page_renders_html_shell() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert "HealthyVytals" in body
    # The base layout must load the vendored HTMX script and the stylesheet.
    assert "htmx.min.js" in body
    assert "app.css" in body


def test_landing_page_wires_htmx_button_to_status() -> None:
    body = client.get("/").text
    # The smoke-test button issues an hx-get to the status partial route.
    assert "hx-get" in body
    assert "/_status" in body
    assert 'hx-target="#status"' in body


def test_status_partial_returns_bare_fragment() -> None:
    response = client.get("/_status")
    assert response.status_code == 200
    body = response.text
    assert "System status" in body
    assert "ok" in body
    # A partial is a fragment, not a full document.
    assert "<html" not in body.lower()


def test_static_css_is_served() -> None:
    response = client.get("/static/app.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]


def test_static_htmx_is_served() -> None:
    response = client.get("/static/htmx.min.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_web_routes_are_hidden_from_openapi() -> None:
    """HTML routes should not clutter the JSON API's OpenAPI schema."""
    schema = client.get("/openapi.json").json()
    assert "/" not in schema["paths"]
    assert "/_status" not in schema["paths"]
