"""Tests for the notification service (app.services.notification_service)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.models.base import Base
from app.models.user import User
from app.services import notification_service


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s
    engine.dispose()


def _user(session: Session) -> User:
    u = User(email="u@example.com", password_hash="h", role=Role.PATIENT)
    session.add(u)
    session.flush()
    return u


def test_notify_and_unread_count(session: Session) -> None:
    u = _user(session)
    notification_service.notify(session, user_id=u.id, event_type="lab.resulted", message="A result")
    notification_service.notify(session, user_id=u.id, event_type="message.received", message="A message")
    assert notification_service.unread_count(session, u.id) == 2
    assert len(notification_service.list_for_user(session, u.id)) == 2


def test_mark_read_is_scoped_and_idempotent(session: Session) -> None:
    u = _user(session)
    other = User(email="o@example.com", password_hash="h", role=Role.PATIENT)
    session.add(other)
    session.flush()
    n = notification_service.notify(session, user_id=u.id, event_type="x", message="m")

    # Another user cannot mark it read.
    assert notification_service.mark_read(session, other.id, n.id) is False
    assert notification_service.unread_count(session, u.id) == 1

    # Owner marks it read; a second call is a no-op.
    assert notification_service.mark_read(session, u.id, n.id) is True
    first_read_at = n.read_at
    assert notification_service.mark_read(session, u.id, n.id) is True
    assert n.read_at == first_read_at
    assert notification_service.unread_count(session, u.id) == 0


def test_mark_all_read(session: Session) -> None:
    u = _user(session)
    for i in range(3):
        notification_service.notify(session, user_id=u.id, event_type="x", message=f"m{i}")
    assert notification_service.mark_all_read(session, u.id) == 3
    assert notification_service.unread_count(session, u.id) == 0
