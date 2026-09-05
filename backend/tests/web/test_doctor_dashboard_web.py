"""Web tests for the doctor dashboard/worklist (M7.2, M7.3)."""

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
        slot = AvailabilitySlot(doctor_id=doc.id, start_at=BASE, end_at=BASE + timedelta(minutes=30), is_booked=True)
        s.add(slot)
        s.flush()
        appt = Appointment(patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id,
                           status=AppointmentStatus.CONFIRMED, reason="Cough")
        s.add(appt)
        s.commit()
        return {"appt": appt.id}


def _login(client: TestClient, email: str) -> None:
    client.post("/login", data={"email": email, "password": PW})


def test_doctor_worklist_shows_appointment(client: TestClient, world: dict[str, int]) -> None:
    _login(client, "doc@example.com")
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    body = resp.text
    assert "Worklist" in body
    assert "pat@example.com" in body        # the booked patient
    assert "Cough" in body                  # reason
    assert "Open encounter" in body         # action available for a confirmed appt


def test_open_encounter_from_worklist_redirects_to_encounter(
    client: TestClient, world: dict[str, int]
) -> None:
    _login(client, "doc@example.com")
    resp = client.post(
        f"/clinical/appointments/{world['appt']}/open", follow_redirects=False
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/clinical/encounters/")

    # Following it lands on the encounter page (diagnose/prescribe forms present).
    page = client.get(resp.headers["location"])
    assert page.status_code == 200
    assert "Add a diagnosis" in page.text


def test_patient_cannot_open_encounter(client: TestClient, world: dict[str, int]) -> None:
    client.post("/register", data={"email": "someone@example.com", "password": PW})
    resp = client.post(f"/clinical/appointments/{world['appt']}/open", follow_redirects=False)
    assert resp.status_code == 403
