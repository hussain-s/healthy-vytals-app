"""Tests for the app factory and the /api/v1/health endpoint.

Verify the versioned mount path, the health payload shape, and that the DB probe
reports connectivity. Uses FastAPI's TestClient (httpx transport) against an app
built by the factory.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db import session as db_session
from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A TestClient backed by a fresh temp SQLite database."""
    db_file = tmp_path / "health.db"
    monkeypatch.setenv("HV_DATABASE_URL", f"sqlite:///{db_file}")
    for cached in (get_settings, db_session.get_engine, db_session.get_sessionmaker):
        cached.cache_clear()

    with TestClient(create_app()) as test_client:
        yield test_client

    db_session.get_engine().dispose()
    for cached in (get_settings, db_session.get_engine, db_session.get_sessionmaker):
        cached.cache_clear()


def test_health_is_mounted_under_versioned_prefix(client: TestClient) -> None:
    """Health must live at /api/v1/health — the versioned API surface."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_reports_ok_and_database_reachable(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    body = response.json()
    assert body == {"status": "ok", "database": "ok"}


def test_unversioned_health_path_is_not_found(client: TestClient) -> None:
    """There is no unversioned /health — the API is versioned from day one."""
    assert client.get("/health").status_code == 404


def test_openapi_docs_available_in_development(client: TestClient) -> None:
    """Interactive docs are served in non-production environments."""
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
