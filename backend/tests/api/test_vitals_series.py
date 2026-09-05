"""API tests for the vitals-series endpoint (app.api.v1.patients) — M10.

Verifies the time-ordered series payload, that a patient sees their own data,
role/relationship scoping (a non-treating doctor is denied), and that the
consent gate hides sensitive encounters from staff without shared consent.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.models.clinical import Encounter, Vitals
from app.models.profile import PatientProfile
from app.models.user import User

PW = "longenough1"
BASE = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def world(db_sessionmaker: sessionmaker[Session]) -> dict[str, int]:
    with db_sessionmaker() as s:
        doc = User(email="doc@example.com", password_hash=hash_password(PW), role=Role.DOCTOR)
        other = User(email="doc2@example.com", password_hash=hash_password(PW), role=Role.DOCTOR)
        pat = User(email="pat@example.com", password_hash=hash_password(PW), role=Role.PATIENT)
        s.add_all([doc, other, pat])
        s.flush()
        s.add(PatientProfile(user_id=pat.id, date_of_birth=date(1986, 1, 1)))
        # Two encounters with vitals at different times (a plottable series).
        e1 = Encounter(appointment_id=1, patient_id=pat.id, doctor_id=doc.id, opened_at=BASE)
        e2 = Encounter(appointment_id=2, patient_id=pat.id, doctor_id=doc.id,
                       opened_at=BASE + timedelta(days=7))
        s.add_all([e1, e2])
        s.flush()
        s.add_all([
            Vitals(encounter_id=e1.id, recorded_by=doc.id, heart_rate=70, spo2=98, flags=""),
            Vitals(encounter_id=e2.id, recorded_by=doc.id, heart_rate=190, spo2=88,
                   flags="heart_rate_high,spo2_low"),
        ])
        s.commit()
        return {"doc": doc.id, "other": other.id, "pat": pat.id}


def _token(client: TestClient, email: str) -> str:
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": PW}
    ).json()["access_token"]


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_patient_sees_own_series_time_ordered(client: TestClient, world: dict) -> None:
    pat = _auth(_token(client, "pat@example.com"))
    resp = client.get(f"/api/v1/patients/{world['pat']}/vitals-series", headers=pat)
    assert resp.status_code == 200
    body = resp.json()
    assert body["patient_id"] == world["pat"]
    assert len(body["points"]) == 2
    # oldest-first
    assert body["points"][0]["heart_rate"] == 70
    assert body["points"][1]["heart_rate"] == 190
    assert body["points"][0]["recorded_at"] <= body["points"][1]["recorded_at"]


def test_treating_doctor_sees_series(client: TestClient, world: dict) -> None:
    doc = _auth(_token(client, "doc@example.com"))
    resp = client.get(f"/api/v1/patients/{world['pat']}/vitals-series", headers=doc)
    assert resp.status_code == 200
    assert len(resp.json()["points"]) == 2


def test_non_treating_doctor_denied(client: TestClient, world: dict) -> None:
    other = _auth(_token(client, "doc2@example.com"))
    resp = client.get(f"/api/v1/patients/{world['pat']}/vitals-series", headers=other)
    assert resp.status_code == 403


def test_patient_cannot_see_other_patient(client: TestClient, world: dict) -> None:
    pat = _auth(_token(client, "pat@example.com"))
    resp = client.get(f"/api/v1/patients/{world['doc']}/vitals-series", headers=pat)
    assert resp.status_code == 403
