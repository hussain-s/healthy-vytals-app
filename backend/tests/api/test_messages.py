"""API tests for messaging & notifications (app.api.v1.messages)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.domain.appointment_state import AppointmentStatus
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


def _token(client: TestClient, email: str) -> str:
    return client.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()[
        "access_token"
    ]


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_send_read_and_notify_flow(client: TestClient, world: dict[str, int]) -> None:
    pat = _token(client, "pat@example.com")
    doc = _token(client, "doc@example.com")

    # Patient sends a message to the treating doctor.
    sent = client.post(
        "/api/v1/messages", headers=_auth(pat),
        json={"counterparty_id": world["doc"], "body": "Hello doctor", "subject": "Question"},
    )
    assert sent.status_code == 201
    thread_id = sent.json()["thread_id"]

    # Doctor sees the thread and reads it.
    threads = client.get("/api/v1/messages/threads", headers=_auth(doc))
    assert threads.status_code == 200
    assert len(threads.json()) == 1

    detail = client.get(f"/api/v1/messages/threads/{thread_id}", headers=_auth(doc))
    assert detail.status_code == 200
    assert detail.json()["messages"][0]["body"] == "Hello doctor"

    # Doctor has a notification about it.
    notes = client.get("/api/v1/notifications", headers=_auth(doc))
    assert notes.status_code == 200
    assert any(n["event_type"] == "message.received" for n in notes.json())

    # Marking one read returns the change count + the caller's new unread count.
    one = client.post(f"/api/v1/notifications/{notes.json()[0]['id']}/read", headers=_auth(doc))
    assert one.status_code == 200
    assert one.json() == {"updated": 1, "unread_count": 0}

    # Doctor marks all read; response reports the new unread count (0) and the
    # feed now has no unread rows.
    read_all = client.post("/api/v1/notifications/read-all", headers=_auth(doc))
    assert read_all.status_code == 200
    assert read_all.json()["unread_count"] == 0
    after = client.get("/api/v1/notifications", headers=_auth(doc)).json()
    assert all(n["read_at"] is not None for n in after)


def test_non_participant_cannot_read_thread(
    client: TestClient, world: dict[str, int], db_sessionmaker: sessionmaker[Session]
) -> None:
    pat = _token(client, "pat@example.com")
    sent = client.post(
        "/api/v1/messages", headers=_auth(pat),
        json={"counterparty_id": world["doc"], "body": "Hi"},
    )
    thread_id = sent.json()["thread_id"]

    # An unrelated nurse (not a participant) is denied reading the thread.
    with db_sessionmaker() as s:
        s.add(User(email="nurse2@example.com", password_hash=hash_password(PW), role=Role.NURSE))
        s.commit()
    intruder = _token(client, "nurse2@example.com")
    assert client.get(f"/api/v1/messages/threads/{thread_id}", headers=_auth(intruder)).status_code == 403

    # And an unauthenticated request is rejected outright.
    assert client.get(f"/api/v1/messages/threads/{thread_id}").status_code == 401


def test_patient_cannot_message_non_treating_doctor(
    client: TestClient, world: dict[str, int], db_sessionmaker: sessionmaker[Session]
) -> None:
    with db_sessionmaker() as s:
        s.add(User(email="doc2@example.com", password_hash=hash_password(PW), role=Role.DOCTOR))
        s.commit()
    pat = _token(client, "pat@example.com")
    from sqlalchemy import select
    with db_sessionmaker() as s:
        other_doc_id = s.scalar(select(User.id).where(User.email == "doc2@example.com"))
    resp = client.post(
        "/api/v1/messages", headers=_auth(pat),
        json={"counterparty_id": other_doc_id, "body": "hi"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "permission_denied"
