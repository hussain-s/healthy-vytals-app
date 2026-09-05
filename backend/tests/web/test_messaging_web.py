"""Web tests for messaging & notifications (app.web.messaging, M9.4)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.domain.appointment_state import AppointmentStatus
from app.models.messaging import MessageThread
from app.models.scheduling import Appointment, AvailabilitySlot
from app.models.user import User

PW = "longenough1"
BASE = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def world(db_sessionmaker: sessionmaker[Session]) -> dict[str, int]:
    with db_sessionmaker() as s:
        doc = User(email="doc@example.com", password_hash=hash_password(PW), role=Role.DOCTOR)
        pat = User(email="pat@example.com", password_hash=hash_password(PW), role=Role.PATIENT)
        s.add_all([doc, pat])
        s.flush()
        slot = AvailabilitySlot(doctor_id=doc.id, start_at=BASE, end_at=BASE + timedelta(minutes=30))
        s.add(slot)
        s.flush()
        s.add(Appointment(patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id,
                          status=AppointmentStatus.CONFIRMED))
        s.commit()
        return {"doc": doc.id, "pat": pat.id}


def _login(client: TestClient, email: str) -> None:
    client.post("/login", data={"email": email, "password": PW})


def test_patient_composes_message_and_doctor_replies(
    client: TestClient, world: dict[str, int], db_sessionmaker: sessionmaker[Session]
) -> None:
    # Patient composes a new message to the doctor from the inbox.
    _login(client, "pat@example.com")
    resp = client.post(
        "/messages/compose",
        data={"counterparty_id": world["doc"], "body": "Hello doctor", "subject": "Q"},
    )
    assert resp.status_code == 200
    assert "doc@example.com" in resp.text
    assert "<html" not in resp.text.lower()  # partial
    client.post("/logout")

    # Doctor sees the conversation and replies.
    with db_sessionmaker() as s:
        thread_id = s.scalar(select(MessageThread.id))
    _login(client, "doc@example.com")
    thread = client.get(f"/messages/{thread_id}")
    assert thread.status_code == 200
    assert "Hello doctor" in thread.text

    reply = client.post(f"/messages/{thread_id}/reply", data={"body": "Hello patient"})
    assert reply.status_code == 200
    assert "Hello patient" in reply.text


def test_doctor_gets_notification_and_marks_read(
    client: TestClient, world: dict[str, int], db_sessionmaker: sessionmaker[Session]
) -> None:
    _login(client, "pat@example.com")
    client.post("/messages/compose", data={"counterparty_id": world["doc"], "body": "Hi", "subject": ""})
    client.post("/logout")

    _login(client, "doc@example.com")
    feed = client.get("/notifications")
    assert feed.status_code == 200
    assert "new message" in feed.text.lower()

    # Mark all read; the refreshed feed no longer offers a "Mark read" button.
    after = client.post("/notifications/read-all")
    assert after.status_code == 200
    assert "Mark read" not in after.text


def test_non_participant_thread_forbidden(
    client: TestClient, world: dict[str, int], db_sessionmaker: sessionmaker[Session]
) -> None:
    _login(client, "pat@example.com")
    client.post("/messages/compose", data={"counterparty_id": world["doc"], "body": "Hi", "subject": ""})
    client.post("/logout")

    with db_sessionmaker() as s:
        s.add(User(email="nurse2@example.com", password_hash=hash_password(PW), role=Role.NURSE))
        s.commit()
        thread_id = s.scalar(select(MessageThread.id))
    _login(client, "nurse2@example.com")
    assert client.get(f"/messages/{thread_id}").status_code == 403
