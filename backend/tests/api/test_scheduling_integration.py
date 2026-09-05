"""Phase 2 exit-gate integration test: the full scheduling journey (DESIGN §9).

Pins the Phase 2 acceptance criteria as one story:
    * a doctor publishes a slot; a patient books it;
    * staff advance the appointment through its lifecycle;
    * a second patient cannot double-book the same slot;
    * a late cancellation is flagged.

Exercises the JSON API end to end via the shared client fixture. Staff are
provisioned by an admin (not self-service).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.models.user import User

PW = "longenough1"


@pytest.fixture
def staff(db_sessionmaker: sessionmaker[Session]) -> None:
    """Seed a doctor and a nurse directly (staff are admin-provisioned)."""
    with db_sessionmaker() as s:
        s.add_all(
            [
                User(email="doc@example.com", password_hash=hash_password(PW), role=Role.DOCTOR),
                User(email="nurse@example.com", password_hash=hash_password(PW), role=Role.NURSE),
            ]
        )
        s.commit()


def _token(client: TestClient, email: str) -> str:
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": PW}
    ).json()["access_token"]


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _future(hours: int) -> tuple[str, str]:
    start = datetime.now(timezone.utc) + timedelta(hours=hours)
    return start.isoformat(), (start + timedelta(minutes=30)).isoformat()


def _doctor_id(client: TestClient, doctor_token: str) -> int:
    return client.get("/api/v1/auth/me", headers=_auth(doctor_token)).json()["id"]


def test_phase2_exit_gate(client: TestClient, staff: None) -> None:
    doc = _token(client, "doc@example.com")
    nurse = _token(client, "nurse@example.com")

    # 1. Doctor publishes a slot (well in the future so cancel isn't "late").
    start, end = _future(72)
    slot = client.post(
        "/api/v1/appointments/slots", headers=_auth(doc), json={"start_at": start, "end_at": end}
    )
    assert slot.status_code == 201
    slot_id = slot.json()["id"]

    # 2. A patient books it.
    client.post("/api/v1/auth/register", json={"email": "pat@example.com", "password": PW})
    pat = _token(client, "pat@example.com")
    booked = client.post(
        "/api/v1/appointments", headers=_auth(pat), json={"slot_id": slot_id, "reason": "cough"}
    )
    assert booked.status_code == 201
    appt_id = booked.json()["id"]

    # 3. A second patient cannot double-book the same slot.
    client.post("/api/v1/auth/register", json={"email": "pat2@example.com", "password": PW})
    pat2 = _token(client, "pat2@example.com")
    dupe = client.post("/api/v1/appointments", headers=_auth(pat2), json={"slot_id": slot_id})
    assert dupe.status_code == 409

    # 4. Staff advance the lifecycle: doctor confirms, nurse checks in, doctor
    #    begins and completes.
    assert client.post(
        f"/api/v1/appointments/{appt_id}/transitions/confirm", headers=_auth(doc)
    ).json()["status"] == "confirmed"
    assert client.post(
        f"/api/v1/appointments/{appt_id}/transitions/check_in", headers=_auth(nurse)
    ).json()["status"] == "checked_in"
    assert client.post(
        f"/api/v1/appointments/{appt_id}/transitions/begin", headers=_auth(doc)
    ).json()["status"] == "in_progress"
    assert client.post(
        f"/api/v1/appointments/{appt_id}/transitions/complete", headers=_auth(doc)
    ).json()["status"] == "completed"


def test_late_cancellation_is_flagged(client: TestClient, staff: None) -> None:
    doc = _token(client, "doc@example.com")
    # Slot only 1 hour away → inside the 24h cutoff.
    start, end = _future(1)
    slot_id = client.post(
        "/api/v1/appointments/slots", headers=_auth(doc), json={"start_at": start, "end_at": end}
    ).json()["id"]

    client.post("/api/v1/auth/register", json={"email": "pat@example.com", "password": PW})
    pat = _token(client, "pat@example.com")
    appt_id = client.post(
        "/api/v1/appointments", headers=_auth(pat), json={"slot_id": slot_id}
    ).json()["id"]

    cancelled = client.post(
        f"/api/v1/appointments/{appt_id}/transitions/cancel", headers=_auth(pat)
    )
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["status"] == "cancelled"
    assert body["cancelled_late"] is True

    # The freed slot is bookable again.
    reopened = client.get(
        f"/api/v1/appointments/slots/open/{_doctor_id(client, doc)}", headers=_auth(pat)
    )
    assert any(s["id"] == slot_id for s in reopened.json())
