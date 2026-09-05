"""Tests for the audit service (app.services.audit_service)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.audit import AuditLog
from app.models.base import Base
from app.services.audit_service import record_audit


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s
    engine.dispose()


def test_record_audit_appends_row_and_flushes(session: Session) -> None:
    entry = record_audit(
        session,
        action="auth.login",
        actor_id=None,
        resource_type="user",
        resource_id=7,
    )
    # Flushed: id is available immediately, resource_id coerced to text.
    assert entry.id is not None
    assert entry.resource_id == "7"


def test_record_audit_does_not_commit(session: Session) -> None:
    """The helper must leave the commit to the caller's unit of work."""
    record_audit(session, action="auth.login_failed")
    session.rollback()  # simulate the enclosing unit of work rolling back

    remaining = session.scalars(select(AuditLog)).all()
    assert remaining == []


def test_record_audit_is_atomic_with_caller(session: Session) -> None:
    """When the caller commits, the audit row is durably persisted."""
    record_audit(session, action="user.register", resource_type="user", resource_id=1)
    session.commit()

    stored = session.scalars(select(AuditLog)).all()
    assert len(stored) == 1
    assert stored[0].action == "user.register"


def test_record_audit_commit_survives_rollback(session: Session) -> None:
    """commit=True persists the row even if the caller later rolls back.

    This is the failed-login case: the audit must outlive the rollback that the
    subsequent InvalidCredentials raise triggers in the request unit of work.
    """
    record_audit(session, action="auth.login_failed", commit=True)
    session.rollback()  # simulate the request rollback after the raise

    stored = session.scalars(select(AuditLog)).all()
    assert len(stored) == 1
    assert stored[0].action == "auth.login_failed"
