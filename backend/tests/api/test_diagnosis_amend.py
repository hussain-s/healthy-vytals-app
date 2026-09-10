"""API tests for diagnosis amendment (NEW feature)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.domain.appointment_state import AppointmentStatus
from app.models.clinical import Diagnosis, Encounter
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
        appt = Appointment(patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id,
                           status=AppointmentStatus.IN_PROGRESS)
        s.add(appt)
        s.flush()
        enc = Encounter(appointment_id=appt.id, patient_id=pat.id, doctor_id=doc.id, opened_at=BASE)
        s.add(enc)
        s.flush()
        dx = Diagnosis(encounter_id=enc.id, author_id=doc.id, icd_code="J06.9",
                       description="Acute URI")
        s.add(dx)
        s.commit()
        return {"dx": dx.id}


def _token(client: TestClient, email: str) -> str:
    return client.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()[
        "access_token"
    ]


def test_owning_doctor_amends_diagnosis(client: TestClient, world: dict[str, int]) -> None:
    doc = _token(client, "doc@example.com")
    resp = client.patch(f"/api/v1/encounters/diagnoses/{world['dx']}",
                        headers={"Authorization": f"Bearer {doc}"},
                        json={"description": "Acute upper respiratory infection"})
    assert resp.status_code == 200
    assert resp.json()["description"] == "Acute upper respiratory infection"


def test_non_doctor_cannot_amend(client: TestClient, world: dict[str, int]) -> None:
    pat = _token(client, "pat@example.com")
    resp = client.patch(f"/api/v1/encounters/diagnoses/{world['dx']}",
                        headers={"Authorization": f"Bearer {pat}"},
                        json={"description": "hax"})
    assert resp.status_code == 403
