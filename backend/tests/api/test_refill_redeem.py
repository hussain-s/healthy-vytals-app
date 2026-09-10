"""API tests for prescription refill redemption (NEW feature)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.domain.appointment_state import AppointmentStatus
from app.models.clinical import Encounter
from app.models.prescription import Medication, Prescription
from app.models.scheduling import Appointment, AvailabilitySlot
from app.models.user import User

PW = "longenough1"
BASE = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def world(db_sessionmaker: sessionmaker[Session]) -> dict[str, int]:
    with db_sessionmaker() as s:
        doc = User(email="doc@example.com", password_hash=hash_password(PW), role=Role.DOCTOR)
        pat = User(email="pat@example.com", password_hash=hash_password(PW), role=Role.PATIENT)
        med = Medication(name="Amoxicillin")
        s.add_all([doc, pat, med])
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
        rx = Prescription(encounter_id=enc.id, patient_id=pat.id, prescriber_id=doc.id,
                          medication_id=med.id, dose="500mg", refills=2)
        s.add(rx)
        s.commit()
        return {"rx": rx.id, "pat": pat.id}


def _token(client: TestClient, email: str) -> str:
    return client.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()[
        "access_token"
    ]


def test_patient_redeems_refills_until_exhausted(client: TestClient, world: dict[str, int]) -> None:
    pat = _token(client, "pat@example.com")
    h = {"Authorization": f"Bearer {pat}"}

    r1 = client.post(f"/api/v1/prescriptions/{world['rx']}/redeem", headers=h)
    assert r1.status_code == 200 and r1.json()["refills_remaining"] == 1

    r2 = client.post(f"/api/v1/prescriptions/{world['rx']}/redeem", headers=h)
    assert r2.status_code == 200 and r2.json()["refills_remaining"] == 0

    r3 = client.post(f"/api/v1/prescriptions/{world['rx']}/redeem", headers=h)
    assert r3.status_code == 409
    assert r3.json()["code"] == "no_refills_remaining"


def test_cannot_redeem_others_prescription(
    client: TestClient, world: dict[str, int], db_sessionmaker: sessionmaker[Session]
) -> None:
    with db_sessionmaker() as s:
        s.add(User(email="pat2@example.com", password_hash=hash_password(PW), role=Role.PATIENT))
        s.commit()
    other = _token(client, "pat2@example.com")
    resp = client.post(f"/api/v1/prescriptions/{world['rx']}/redeem",
                       headers={"Authorization": f"Bearer {other}"})
    assert resp.status_code == 403
