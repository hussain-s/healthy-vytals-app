"""API tests for the AI vitals-assessment endpoint (app.api.v1.encounters).

Exercises POST /api/v1/encounters/{id}/vitals-assessment end-to-end over HTTP with
the default offline stub provider (no API key/SDK needed). Verifies role gating,
the treating-relationship rule for doctors, the "record vitals first" precondition,
and that the response is the structured advisory contract.
"""

from __future__ import annotations

from collections.abc import Iterator
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
        other = User(email="doc2@example.com", password_hash=hash_password(PW), role=Role.DOCTOR)
        nurse = User(email="nurse@example.com", password_hash=hash_password(PW), role=Role.NURSE)
        pat = User(email="pat@example.com", password_hash=hash_password(PW), role=Role.PATIENT)
        s.add_all([doc, other, nurse, pat])
        s.flush()
        s.add(PatientProfile(user_id=pat.id, date_of_birth=date(1986, 1, 1)))
        slot = AvailabilitySlot(doctor_id=doc.id, start_at=BASE, end_at=BASE + timedelta(minutes=30))
        s.add(slot)
        s.flush()
        appt = Appointment(
            patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id,
            status=AppointmentStatus.IN_PROGRESS,
        )
        s.add(appt)
        s.commit()
        return {"doc": doc.id, "other": other.id, "nurse": nurse.id,
                "pat": pat.id, "appt": appt.id}


def _token(client: TestClient, email: str) -> str:
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": PW}
    ).json()["access_token"]


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _open_encounter_with_vitals(client: TestClient) -> int:
    """Doctor opens an encounter; nurse records vitals. Returns the encounter id."""
    doc = _auth(_token(client, "doc@example.com"))
    nurse = _auth(_token(client, "nurse@example.com"))
    enc = client.post("/api/v1/encounters", json={"appointment_id": 1}, headers=doc)
    enc_id = enc.json()["id"]
    client.post(
        f"/api/v1/encounters/{enc_id}/vitals",
        json={"heart_rate": 190, "spo2": 88},  # clearly abnormal for an adult
        headers=nurse,
    )
    return enc_id


def test_nurse_gets_structured_assessment(client: TestClient, world: dict) -> None:
    enc_id = _open_encounter_with_vitals(client)
    nurse = _auth(_token(client, "nurse@example.com"))
    resp = client.post(f"/api/v1/encounters/{enc_id}/vitals-assessment", headers=nurse)
    assert resp.status_code == 200
    body = resp.json()
    # structured advisory contract, and the rule-detected abnormality is honored
    assert set(body) == {"summary", "urgency", "red_flags", "recommended_action", "confidence"}
    assert body["urgency"] != "routine"  # real flags present → never routine
    assert 0.0 <= body["confidence"] <= 1.0


def test_treating_doctor_allowed(client: TestClient, world: dict) -> None:
    enc_id = _open_encounter_with_vitals(client)
    doc = _auth(_token(client, "doc@example.com"))  # the treating doctor
    resp = client.post(f"/api/v1/encounters/{enc_id}/vitals-assessment", headers=doc)
    assert resp.status_code == 200


def test_non_treating_doctor_denied(client: TestClient, world: dict) -> None:
    enc_id = _open_encounter_with_vitals(client)
    other = _auth(_token(client, "doc2@example.com"))  # no treating relationship
    resp = client.post(f"/api/v1/encounters/{enc_id}/vitals-assessment", headers=other)
    assert resp.status_code == 403


def test_patient_forbidden_by_role_gate(client: TestClient, world: dict) -> None:
    enc_id = _open_encounter_with_vitals(client)
    pat = _auth(_token(client, "pat@example.com"))
    resp = client.post(f"/api/v1/encounters/{enc_id}/vitals-assessment", headers=pat)
    assert resp.status_code == 403


def test_requires_vitals_recorded_first(client: TestClient, world: dict) -> None:
    """Assessing an encounter with no vitals yet is a 404, not a crash."""
    doc = _auth(_token(client, "doc@example.com"))
    enc = client.post("/api/v1/encounters", json={"appointment_id": 1}, headers=doc)
    enc_id = enc.json()["id"]
    nurse = _auth(_token(client, "nurse@example.com"))
    resp = client.post(f"/api/v1/encounters/{enc_id}/vitals-assessment", headers=nurse)
    assert resp.status_code == 404
