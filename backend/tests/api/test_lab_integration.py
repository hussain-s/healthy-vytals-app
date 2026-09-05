"""M8 exit-gate integration test: doctor orders → nurse records → patient/doctor view.

Pins the M8 acceptance narrative (DESIGN §13.2) over the JSON API: a doctor orders
a lab, a nurse records an abnormal result, and both the patient and the treating
doctor see it (flagged), while a non-treating doctor is denied.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.domain.appointment_state import AppointmentStatus
from app.models.audit import AuditLog
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


def _tok(client: TestClient, email: str) -> dict[str, str]:
    t = client.post("/api/v1/auth/login", json={"email": email, "password": PW}).json()["access_token"]
    return {"Authorization": f"Bearer {t}"}


def test_m8_exit_gate(
    client: TestClient, world: dict[str, int], db_sessionmaker: sessionmaker[Session]
) -> None:
    doc, nurse, pat = (_tok(client, e) for e in
                       ("doc@example.com", "nurse@example.com", "pat@example.com"))

    # Doctor orders.
    order_id = client.post(
        "/api/v1/labs/orders", headers=doc,
        json={"encounter_id": world["enc"], "test_code": "CBC", "test_name": "Complete Blood Count"},
    ).json()["id"]

    # Nurse records an abnormal result.
    res = client.post(
        f"/api/v1/labs/orders/{order_id}/results", headers=nurse,
        json={"analyte": "Hemoglobin", "value": 8.0, "unit": "g/dL",
              "reference_low": 12.0, "reference_high": 17.0},
    )
    assert res.status_code == 201 and res.json()["abnormal"] is True

    # Patient and treating doctor both see the (resulted) order.
    for who in (pat, doc):
        labs = client.get(f"/api/v1/labs/patient/{world['pat']}", headers=who)
        assert labs.status_code == 200
        assert len(labs.json()) == 1
        assert labs.json()[0]["status"] == "resulted"

    # A non-treating doctor is denied.
    with db_sessionmaker() as s:
        s.add(User(email="doc2@example.com", password_hash=hash_password(PW), role=Role.DOCTOR))
        s.commit()
    other = _tok(client, "doc2@example.com")
    assert client.get(f"/api/v1/labs/patient/{world['pat']}", headers=other).status_code == 403

    # Audit trail covers the whole flow.
    with db_sessionmaker() as s:
        actions = set(s.scalars(select(AuditLog.action)).all())
    assert {"lab.order", "lab.result", "lab.read", "lab.read_denied"} <= actions
