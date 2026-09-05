"""API tests for prescribing (app.api.v1.prescriptions)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.domain.appointment_state import AppointmentStatus
from app.models.clinical import Encounter
from app.models.prescription import Allergy, Medication
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
        amox = Medication(name="Amoxicillin", drug_class="penicillin")
        oxy = Medication(name="Oxycodone", drug_class="opioid", is_controlled=True)
        s.add_all([amox, oxy])
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
        return {"doc": doc.id, "pat": pat.id, "amox": amox.id, "oxy": oxy.id, "enc": enc.id}


def _token(client: TestClient, email: str) -> str:
    return client.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()[
        "access_token"
    ]


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_safe_prescription_succeeds(client: TestClient, world: dict[str, int]) -> None:
    doc = _token(client, "doc@example.com")
    resp = client.post(
        "/api/v1/prescriptions",
        headers=_auth(doc),
        json={"encounter_id": world["enc"], "medication_id": world["amox"], "dose": "500mg", "refills": 2},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "active"


def test_allergy_blocks_with_reason(
    client: TestClient, world: dict[str, int], db_sessionmaker: sessionmaker[Session]
) -> None:
    with db_sessionmaker() as s:
        s.add(Allergy(patient_id=world["pat"], substance="penicillin"))
        s.commit()
    doc = _token(client, "doc@example.com")
    resp = client.post(
        "/api/v1/prescriptions",
        headers=_auth(doc),
        json={"encounter_id": world["enc"], "medication_id": world["amox"], "dose": "500mg"},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["code"] == "unsafe_prescription"
    assert body["details"]["reason"] == "allergy"


def test_controlled_refill_cap_blocks(client: TestClient, world: dict[str, int]) -> None:
    doc = _token(client, "doc@example.com")
    resp = client.post(
        "/api/v1/prescriptions",
        headers=_auth(doc),
        json={"encounter_id": world["enc"], "medication_id": world["oxy"], "dose": "5mg", "refills": 3},
    )
    assert resp.status_code == 409
    assert resp.json()["details"]["reason"] == "refill_cap"


def test_patient_cannot_prescribe(client: TestClient, world: dict[str, int]) -> None:
    pat = _token(client, "pat@example.com")
    resp = client.post(
        "/api/v1/prescriptions",
        headers=_auth(pat),
        json={"encounter_id": world["enc"], "medication_id": world["amox"], "dose": "500mg"},
    )
    assert resp.status_code == 403


def test_patient_views_own_prescriptions(client: TestClient, world: dict[str, int]) -> None:
    doc = _token(client, "doc@example.com")
    client.post(
        "/api/v1/prescriptions",
        headers=_auth(doc),
        json={"encounter_id": world["enc"], "medication_id": world["amox"], "dose": "500mg"},
    )
    pat = _token(client, "pat@example.com")
    resp = client.get("/api/v1/prescriptions/mine", headers=_auth(pat))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
