"""API tests for the clinical endpoints (app.api.v1.encounters).

Exercises the full clinical flow over HTTP via the shared client fixture: a
doctor opens an encounter, a nurse records (flagged) vitals, the doctor adds a
diagnosis, and history reads are scoped by the treating-relationship rule.
Staff are seeded directly; a slot+appointment is created so an encounter can open.
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
    """Seed doctor, nurse, patient (with DOB), a slot, and an in-progress appt."""
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
        appt = Appointment(
            patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id, status=AppointmentStatus.IN_PROGRESS
        )
        s.add(appt)
        s.commit()
        return {"doc": doc.id, "nurse": nurse.id, "pat": pat.id, "appt": appt.id}


def _token(client: TestClient, email: str) -> str:
    return client.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()[
        "access_token"
    ]


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_full_clinical_flow(client: TestClient, world: dict[str, int]) -> None:
    doc = _token(client, "doc@example.com")
    nurse = _token(client, "nurse@example.com")

    # Doctor opens the encounter.
    enc = client.post("/api/v1/encounters", headers=_auth(doc), json={"appointment_id": world["appt"]})
    assert enc.status_code == 201
    enc_id = enc.json()["id"]

    # Nurse records vitals; adult HR 150 is flagged high.
    vitals = client.post(
        f"/api/v1/encounters/{enc_id}/vitals",
        headers=_auth(nurse),
        json={"heart_rate": 150, "spo2": 98},
    )
    assert vitals.status_code == 201
    assert "heart_rate_high" in vitals.json()["flags"]

    # Doctor adds a diagnosis.
    dx = client.post(
        f"/api/v1/encounters/{enc_id}/diagnoses",
        headers=_auth(doc),
        json={"icd_code": "J06.9", "description": "Acute URI"},
    )
    assert dx.status_code == 201


def test_nurse_cannot_open_encounter(client: TestClient, world: dict[str, int]) -> None:
    nurse = _token(client, "nurse@example.com")
    resp = client.post(
        "/api/v1/encounters", headers=_auth(nurse), json={"appointment_id": world["appt"]}
    )
    assert resp.status_code == 403


def test_doctor_cannot_record_vitals(client: TestClient, world: dict[str, int]) -> None:
    """Vitals are nurse-authored; a doctor is 403 (coarse role gate)."""
    doc = _token(client, "doc@example.com")
    enc_id = client.post(
        "/api/v1/encounters", headers=_auth(doc), json={"appointment_id": world["appt"]}
    ).json()["id"]
    resp = client.post(
        f"/api/v1/encounters/{enc_id}/vitals", headers=_auth(doc), json={"heart_rate": 70}
    )
    assert resp.status_code == 403


def test_history_scoping_over_http(client: TestClient, world: dict[str, int]) -> None:
    doc = _token(client, "doc@example.com")
    client.post("/api/v1/encounters", headers=_auth(doc), json={"appointment_id": world["appt"]})

    # Treating doctor reads the patient's history.
    ok = client.get(f"/api/v1/encounters/history/{world['pat']}", headers=_auth(doc))
    assert ok.status_code == 200
    assert len(ok.json()) == 1

    # A patient cannot read another patient's history.
    client.post("/api/v1/auth/register", json={"email": "other@example.com", "password": PW})
    other = _token(client, "other@example.com")
    denied = client.get(f"/api/v1/encounters/history/{world['pat']}", headers=_auth(other))
    assert denied.status_code == 403
    assert denied.json()["code"] == "permission_denied"


def test_patient_reads_own_history(client: TestClient, world: dict[str, int]) -> None:
    doc = _token(client, "doc@example.com")
    client.post("/api/v1/encounters", headers=_auth(doc), json={"appointment_id": world["appt"]})
    pat = _token(client, "pat@example.com")
    resp = client.get(f"/api/v1/encounters/history/{world['pat']}", headers=_auth(pat))
    assert resp.status_code == 200
    assert len(resp.json()) == 1
