"""Shared pytest fixtures for HealthyVytals backend tests.

Provides an API ``client`` backed by an isolated, schema-created SQLite database
per test, with the app's ``get_session`` dependency overridden to use it. This is
the standard harness for API/web integration tests (DESIGN §10).

Isolation strategy: a single in-memory SQLite database shared across connections
within one test (via ``StaticPool``), created fresh per test function so tests
never see each other's rows.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import get_session
from app.main import create_app
from app.models.base import Base


@pytest.fixture
def db_sessionmaker() -> Iterator[sessionmaker[Session]]:
    """A sessionmaker on a fresh in-memory SQLite DB with the schema created.

    StaticPool keeps a single underlying connection so every session in the test
    sees the same in-memory database (in-memory SQLite is per-connection).
    """
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    engine.dispose()


@pytest.fixture
def client(db_sessionmaker: sessionmaker[Session]) -> Iterator[TestClient]:
    """A TestClient whose get_session dependency uses the test database.

    The override mirrors the real get_session transactional contract: commit on
    success, rollback on error, always close.
    """

    def _override_get_session() -> Iterator[Session]:
        session = db_sessionmaker()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app = create_app()
    app.dependency_overrides[get_session] = _override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
