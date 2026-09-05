"""API tests for the lab flow (app.api.v1.labs)."""

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
        return {"enc": enc.id, "pat": pat.id}


def _token(client: TestClient, email: str) -> str:
    return client.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()[
        "access_token"
    ]


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_full_lab_flow(client: TestClient, world: dict[str, int]) -> None:
    doc = _token(client, "doc@example.com")
    nurse = _token(client, "nurse@example.com")
    pat = _token(client, "pat@example.com")

    # Doctor orders a lab.
    order = client.post(
        "/api/v1/labs/orders",
        headers=_auth(doc),
        json={"encounter_id": world["enc"], "test_code": "CBC", "test_name": "Complete Blood Count"},
    )
    assert order.status_code == 201
    order_id = order.json()["id"]
    assert order.json()["status"] == "ordered"

    # Nurse records an abnormal result.
    result = client.post(
        f"/api/v1/labs/orders/{order_id}/results",
        headers=_auth(nurse),
        json={"analyte": "Hemoglobin", "value": 8.0, "unit": "g/dL",
              "reference_low": 12.0, "reference_high": 17.0},
    )
    assert result.status_code == 201
    assert result.json()["abnormal"] is True

    # Patient sees the order (now resulted).
    mine = client.get(f"/api/v1/labs/patient/{world['pat']}", headers=_auth(pat))
    assert mine.status_code == 200
    assert len(mine.json()) == 1
    assert mine.json()[0]["status"] == "resulted"


def test_patient_cannot_order_lab(client: TestClient, world: dict[str, int]) -> None:
    pat = _token(client, "pat@example.com")
    resp = client.post(
        "/api/v1/labs/orders",
        headers=_auth(pat),
        json={"encounter_id": world["enc"], "test_code": "CBC", "test_name": "CBC"},
    )
    assert resp.status_code == 403


def test_non_treating_doctor_denied_patient_labs(
    client: TestClient, world: dict[str, int], db_sessionmaker: sessionmaker[Session]
) -> None:
    with db_sessionmaker() as s:
        s.add(User(email="doc2@example.com", password_hash=hash_password(PW), role=Role.DOCTOR))
        s.commit()
    other = _token(client, "doc2@example.com")
    resp = client.get(f"/api/v1/labs/patient/{world['pat']}", headers=_auth(other))
    assert resp.status_code == 403
    assert resp.json()["code"] == "permission_denied"
