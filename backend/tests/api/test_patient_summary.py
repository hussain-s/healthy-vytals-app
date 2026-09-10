"""API tests for the patient clinical summary (NEW feature)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.domain.appointment_state import AppointmentStatus
from app.models.clinical import Encounter
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
        slot = AvailabilitySlot(doctor_id=doc.id, start_at=BASE, end_at=BASE + timedelta(minutes=30))
        s.add(slot)
        s.flush()
        appt = Appointment(patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id,
                           status=AppointmentStatus.IN_PROGRESS)
        s.add(appt)
        s.flush()
        enc = Encounter(appointment_id=appt.id, patient_id=pat.id, doctor_id=doc.id, opened_at=BASE)
        s.add(enc)
        s.commit()
        return {"pat": pat.id}


def _token(client: TestClient, email: str) -> str:
    return client.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()[
        "access_token"
    ]


def test_treating_doctor_sees_summary(client: TestClient, world: dict[str, int]) -> None:
    doc = _token(client, "doc@example.com")
    resp = client.get(f"/api/v1/patients/{world['pat']}/summary",
                      headers={"Authorization": f"Bearer {doc}"})
    assert resp.status_code == 200
    assert resp.json()["encounter_count"] == 1


def test_patient_cannot_use_staff_summary(client: TestClient, world: dict[str, int]) -> None:
    pat = _token(client, "pat@example.com")
    resp = client.get(f"/api/v1/patients/{world['pat']}/summary",
                      headers={"Authorization": f"Bearer {pat}"})
    assert resp.status_code == 403
