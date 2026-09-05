"""Tests for UserRepository (app.repositories.user_repository)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.models.base import Base
from app.models.user import User
from app.repositories.user_repository import UserRepository


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s
    engine.dispose()


def test_get_by_email_finds_and_misses(session: Session) -> None:
    repo = UserRepository(session)
    repo.add(User(email="pat@example.com", password_hash="h", role=Role.PATIENT))

    found = repo.get_by_email("pat@example.com")
    assert found is not None
    assert found.role is Role.PATIENT
    assert repo.get_by_email("nobody@example.com") is None


def test_email_exists(session: Session) -> None:
    repo = UserRepository(session)
    assert repo.email_exists("pat@example.com") is False
    repo.add(User(email="pat@example.com", password_hash="h", role=Role.PATIENT))
    assert repo.email_exists("pat@example.com") is True


def test_inherits_generic_crud(session: Session) -> None:
    """UserRepository still offers the base get/count operations."""
    repo = UserRepository(session)
    user = repo.add(User(email="a@example.com", password_hash="h", role=Role.ADMIN))
    assert repo.get(user.id) is user
    assert repo.count() == 1
