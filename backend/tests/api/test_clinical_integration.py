"""Phase 3 exit-gate integration test: the clinical journey (DESIGN §9).

Pins the Phase 3 acceptance: the nurse→doctor flow works end to end, and scoping
+ append-only are enforced. Runs over the JSON API via the shared client fixture.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.domain.appointment_state import AppointmentStatus
from app.models.audit import AuditLog
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
        s.add(PatientProfile(user_id=pat.id, date_of_birth=date(2020, 1, 1)))  # young child
        slot = AvailabilitySlot(doctor_id=doc.id, start_at=BASE, end_at=BASE + timedelta(minutes=30))
        s.add(slot)
        s.flush()
        appt = Appointment(patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id,
                           status=AppointmentStatus.IN_PROGRESS)
        s.add(appt)
        s.commit()
        return {"doc": doc.id, "nurse": nurse.id, "pat": pat.id, "appt": appt.id}


def _token(client: TestClient, email: str) -> str:
    return client.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()[
        "access_token"
    ]


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_phase3_exit_gate(
    client: TestClient, world: dict[str, int], db_sessionmaker: sessionmaker[Session]
) -> None:
    doc = _token(client, "doc@example.com")
    nurse = _token(client, "nurse@example.com")
    pat = _token(client, "pat@example.com")

    # Doctor opens the encounter.
    enc_id = client.post(
        "/api/v1/encounters", headers=_auth(doc), json={"appointment_id": world["appt"]}
    ).json()["id"]

    # Nurse records vitals; HR 60 is LOW for a young child (child band 70-120),
    # though it would be normal for an adult — demonstrating the age-based rule.
    vitals = client.post(
        f"/api/v1/encounters/{enc_id}/vitals", headers=_auth(nurse), json={"heart_rate": 60}
    )
    assert vitals.status_code == 201
    assert "heart_rate_low" in vitals.json()["flags"]

    # Doctor diagnoses.
    assert client.post(
        f"/api/v1/encounters/{enc_id}/diagnoses",
        headers=_auth(doc),
        json={"icd_code": "J06.9", "description": "Acute URI"},
    ).status_code == 201

    # Patient sees their own history (one encounter).
    hist = client.get(f"/api/v1/encounters/history/{world['pat']}", headers=_auth(pat))
    assert hist.status_code == 200 and len(hist.json()) == 1

    # A non-treating doctor is denied and the denial is audited.
    with db_sessionmaker() as s:
        s.add(User(email="doc2@example.com", password_hash=hash_password(PW), role=Role.DOCTOR))
        s.commit()
    doc2 = _token(client, "doc2@example.com")
    denied = client.get(f"/api/v1/encounters/history/{world['pat']}", headers=_auth(doc2))
    assert denied.status_code == 403

    with db_sessionmaker() as s:
        actions = set(s.scalars(select(AuditLog.action)).all())
    assert {"encounter.open", "vitals.record", "diagnosis.create",
            "history.read", "history.read_denied"} <= actions


def test_append_only_no_delete_endpoint(client: TestClient, world: dict[str, int]) -> None:
    """Immutability (§5.6): there is no update/delete route for clinical records."""
    doc = _token(client, "doc@example.com")
    enc_id = client.post(
        "/api/v1/encounters", headers=_auth(doc), json={"appointment_id": world["appt"]}
    ).json()["id"]

    # No DELETE/PUT on an encounter — the API surface only creates + addends.
    assert client.delete(f"/api/v1/encounters/{enc_id}", headers=_auth(doc)).status_code in (404, 405)
    assert client.put(f"/api/v1/encounters/{enc_id}", headers=_auth(doc), json={}).status_code in (404, 405)

    # Corrections go through addenda instead.
    add = client.post(
        "/api/v1/encounters/addenda",
        headers=_auth(doc),
        json={"target_type": "encounter", "target_id": enc_id, "note": "clarification"},
    )
    assert add.status_code == 201
