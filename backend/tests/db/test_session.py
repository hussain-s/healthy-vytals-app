"""Tests for the persistence foundation (app.models.base, app.db.session).

These exercise the shared mixins and the *actual* unit-of-work / get_session
transactional semantics against a real temporary SQLite database. We point
HV_DATABASE_URL at a temp file, clear the cached settings/engine/sessionmaker so
the module builds against it, and create a throwaway table so the test does not
depend on any concrete domain model yet.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import String, select
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.db import session as db_session
from app.models.base import Base, IdMixin, TimestampMixin


class _Widget(IdMixin, TimestampMixin, Base):
    """Throwaway model used only to exercise the base/mixins in isolation."""

    __tablename__ = "_test_widget"
    name: Mapped[str] = mapped_column(String(50), nullable=False)


@pytest.fixture
def temp_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Point the app's engine at a fresh temp SQLite file and create the schema.

    Clears the lru_caches for settings/engine/sessionmaker so app.db.session
    rebuilds against the temp database, and restores them afterwards so other
    tests are unaffected.
    """
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("HV_DATABASE_URL", f"sqlite:///{db_file}")

    for cached in (get_settings, db_session.get_engine, db_session.get_sessionmaker):
        cached.cache_clear()

    _Widget.__table__.create(db_session.get_engine())
    try:
        yield
    finally:
        db_session.get_engine().dispose()
        for cached in (get_settings, db_session.get_engine, db_session.get_sessionmaker):
            cached.cache_clear()


def _names() -> list[str]:
    """Read all widget names via a fresh session (independent of the code path)."""
    with db_session.get_sessionmaker()() as session:
        return list(session.scalars(select(_Widget.name)).all())


def test_mixins_populate_id_and_timestamps(temp_db: None) -> None:
    with db_session.unit_of_work() as session:
        widget = _Widget(name="alpha")
        session.add(widget)

    # After the block commits, the row carries a key and both timestamps.
    with db_session.get_sessionmaker()() as verify:
        stored = verify.scalars(select(_Widget)).one()
    assert stored.id is not None
    assert stored.created_at is not None
    assert stored.updated_at is not None


def test_unit_of_work_commits_on_success(temp_db: None) -> None:
    with db_session.unit_of_work() as session:
        session.add(_Widget(name="committed"))

    assert "committed" in _names()


def test_unit_of_work_rolls_back_on_error(temp_db: None) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        with db_session.unit_of_work() as session:
            session.add(_Widget(name="doomed"))
            raise RuntimeError("boom")

    assert "doomed" not in _names()


def test_get_session_commits_on_success(temp_db: None) -> None:
    """The FastAPI dependency generator commits when the consumer finishes."""
    gen = db_session.get_session()
    session = next(gen)
    session.add(_Widget(name="via-dep"))
    with pytest.raises(StopIteration):
        next(gen)  # exhausting the generator runs commit + close

    assert "via-dep" in _names()


def test_get_session_rolls_back_on_error(temp_db: None) -> None:
    """If the consumer raises, get_session must roll back before closing."""
    gen = db_session.get_session()
    session = next(gen)
    session.add(_Widget(name="dep-doomed"))
    with pytest.raises(RuntimeError, match="kaboom"):
        gen.throw(RuntimeError("kaboom"))

    assert "dep-doomed" not in _names()
