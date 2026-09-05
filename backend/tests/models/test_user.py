"""Tests for the User model (app.models.user).

Verifies persistence basics against a real in-memory SQLite schema: the role
enum round-trips as its string value, is_active defaults to True, and the email
uniqueness constraint is enforced.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.models.base import Base
from app.models.user import User


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    # Create the full schema so FK/constraint behavior matches production.
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s
    engine.dispose()


def test_user_persists_with_role_and_defaults(session: Session) -> None:
    user = User(email="pat@example.com", password_hash="hashed", role=Role.PATIENT)
    session.add(user)
    session.commit()

    stored = session.scalar(select(User).where(User.email == "pat@example.com"))
    assert stored is not None
    assert stored.id is not None
    assert stored.role is Role.PATIENT
    assert stored.is_active is True  # server_default applied
    assert stored.created_at is not None


def test_role_round_trips_as_string_value(session: Session) -> None:
    """The role column stores the enum value; reading yields a Role again."""
    session.add(User(email="doc@example.com", password_hash="h", role=Role.DOCTOR))
    session.commit()

    # Confirm the raw stored value is the string "doctor", not "DOCTOR".
    raw = session.execute(
        select(User.role).where(User.email == "doc@example.com")
    ).scalar_one()
    assert raw == Role.DOCTOR
    assert Role(raw) is Role.DOCTOR


def test_email_must_be_unique(session: Session) -> None:
    session.add(User(email="dup@example.com", password_hash="h", role=Role.NURSE))
    session.commit()

    session.add(User(email="dup@example.com", password_hash="h2", role=Role.ADMIN))
    with pytest.raises(IntegrityError):
        session.commit()
