"""Tests for the AuditLog model (app.models.audit)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.user import User


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s
    engine.dispose()


def test_audit_row_persists_with_actor_and_patient(session: Session) -> None:
    actor = User(email="doc@example.com", password_hash="h", role=Role.DOCTOR)
    patient = User(email="pat@example.com", password_hash="h", role=Role.PATIENT)
    session.add_all([actor, patient])
    session.flush()

    entry = AuditLog(
        actor_id=actor.id,
        action="encounter.read",
        resource_type="encounter",
        resource_id="42",
        patient_id=patient.id,
    )
    session.add(entry)
    session.commit()

    assert entry.id is not None
    assert entry.created_at is not None
    assert entry.action == "encounter.read"


def test_actor_id_is_nullable_for_failed_login(session: Session) -> None:
    """A failed login has no authenticated actor but must still be auditable."""
    entry = AuditLog(actor_id=None, action="auth.login_failed")
    session.add(entry)
    session.commit()
    assert entry.id is not None
    assert entry.actor_id is None
