"""Web tests for the AI vitals-assistant panel (app.web.clinical).

Drives the nurse triage flow over the cookie-session web UI with the default
offline stub provider: record vitals, then request the HTMX assessment partial.
Verifies the panel renders, is nurse-gated, and requires vitals first.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.domain.appointment_state import AppointmentStatus
from app.models.profile import PatientProfile
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
        s.add(PatientProfile(user_id=pat.id, date_of_birth=date(1986, 1, 1)))
        slot = AvailabilitySlot(doctor_id=doc.id, start_at=BASE, end_at=BASE + timedelta(minutes=30))
        s.add(slot)
        s.flush()
        appt = Appointment(patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id,
                           status=AppointmentStatus.IN_PROGRESS)
        s.add(appt)
        s.commit()
        return {"nurse": nurse.id, "appt": appt.id}


def _login(client: TestClient, email: str) -> None:
    client.post("/login", data={"email": email, "password": PW})


def test_nurse_records_vitals_then_gets_assessment_panel(
    client: TestClient, world: dict[str, int]
) -> None:
    _login(client, "nurse@example.com")
    appt = world["appt"]
    # Record vitals (creates the encounter); result partial offers the assist button.
    saved = client.post(
        f"/clinical/appointments/{appt}/vitals",
        data={"heart_rate": "190", "spo2": "88"},
    )
    assert saved.status_code == 200
    assert "Get AI triage assist" in saved.text
    # Request the AI assessment partial.
    resp = client.post(f"/clinical/appointments/{appt}/vitals-assessment")
    assert resp.status_code == 200
    assert "AI triage assist" in resp.text
    assert "Advisory only" in resp.text  # the not-a-diagnosis disclaimer


def test_assessment_requires_vitals_first(
    client: TestClient, world: dict[str, int]
) -> None:
    _login(client, "nurse@example.com")
    resp = client.post(f"/clinical/appointments/{world['appt']}/vitals-assessment")
    assert resp.status_code == 404


def test_non_nurse_cannot_use_triage_assist(
    client: TestClient, world: dict[str, int]
) -> None:
    _login(client, "doc@example.com")
    resp = client.post(f"/clinical/appointments/{world['appt']}/vitals-assessment")
    assert resp.status_code == 403
