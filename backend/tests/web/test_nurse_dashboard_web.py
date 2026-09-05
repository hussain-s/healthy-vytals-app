"""Web tests for the nurse ward board + vitals entry (M7.4, M7.5)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.domain.appointment_state import AppointmentStatus
from app.models.clinical import Vitals
from app.models.scheduling import Appointment, AvailabilitySlot
from app.models.user import User

PW = "longenough1"
BASE = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def world(db_sessionmaker: sessionmaker[Session]) -> dict[str, int]:
    with db_sessionmaker() as s:
        doc = User(email="doc@example.com", password_hash=hash_password(PW), role=Role.DOCTOR)
        nurse = User(email="nurse@example.com", password_hash=hash_password(PW), role=Role.NURSE)
        pat = User(email="pat@example.com", password_hash=hash_password(PW), role=Role.PATIENT)
        s.add_all([doc, nurse, pat])
        s.flush()
        slot = AvailabilitySlot(doctor_id=doc.id, start_at=BASE, end_at=BASE + timedelta(minutes=30), is_booked=True)
        s.add(slot)
        s.flush()
        appt = Appointment(patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id,
                           status=AppointmentStatus.CONFIRMED, reason="Cough")
        s.add(appt)
        s.commit()
        return {"appt": appt.id, "pat": pat.id}


def _login(client: TestClient, email: str) -> None:
    client.post("/login", data={"email": email, "password": PW})


def test_ward_board_lists_appointment_with_actions(client: TestClient, world: dict[str, int]) -> None:
    _login(client, "nurse@example.com")
    body = client.get("/dashboard").text
    assert "Ward board" in body
    assert "pat@example.com" in body
    assert "Check in" in body
    assert "Record vitals" in body


def test_check_in_advances_state(client: TestClient, world: dict[str, int]) -> None:
    _login(client, "nurse@example.com")
    resp = client.post(f"/clinical/appointments/{world['appt']}/check-in", follow_redirects=False)
    assert resp.status_code == 303


def test_nurse_records_vitals_flagged(
    client: TestClient, world: dict[str, int], db_sessionmaker: sessionmaker[Session]
) -> None:
    _login(client, "nurse@example.com")
    # Form renders.
    assert client.get(f"/clinical/appointments/{world['appt']}/vitals").status_code == 200
    # Submit a high adult heart rate → flagged.
    resp = client.post(
        f"/clinical/appointments/{world['appt']}/vitals",
        data={"heart_rate": "150", "spo2": "98"},
    )
    assert resp.status_code == 200
    assert "Vitals recorded" in resp.text
    assert "heart_rate_high" in resp.text
    # Persisted.
    with db_sessionmaker() as s:
        assert s.scalar(select(Vitals)) is not None


def test_patient_cannot_record_vitals(client: TestClient, world: dict[str, int]) -> None:
    client.post("/register", data={"email": "p2@example.com", "password": PW})
    resp = client.get(f"/clinical/appointments/{world['appt']}/vitals")
    assert resp.status_code == 403
