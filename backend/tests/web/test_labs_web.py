"""Web tests for the lab flow (app.web.clinical lab routes, M8.5)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.domain.appointment_state import AppointmentStatus
from app.models.clinical import Encounter
from app.models.lab import LabOrder
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
        return {"enc": enc.id}


def _login(client: TestClient, email: str) -> None:
    client.post("/login", data={"email": email, "password": PW})


def _order_id(db_sessionmaker: sessionmaker[Session]) -> int:
    from sqlalchemy import select
    with db_sessionmaker() as s:
        return s.scalar(select(LabOrder.id))


def test_doctor_orders_lab_via_encounter(client: TestClient, world: dict[str, int]) -> None:
    _login(client, "doc@example.com")
    resp = client.post(
        f"/clinical/encounters/{world['enc']}/labs",
        data={"test_code": "CBC", "test_name": "Complete Blood Count", "notes": ""},
    )
    assert resp.status_code == 200
    assert "Complete Blood Count" in resp.text
    assert "<html" not in resp.text.lower()  # partial


def test_nurse_queue_and_record_result(
    client: TestClient, world: dict[str, int], db_sessionmaker: sessionmaker[Session]
) -> None:
    # Doctor orders first.
    _login(client, "doc@example.com")
    client.post(f"/clinical/encounters/{world['enc']}/labs",
                data={"test_code": "CBC", "test_name": "CBC", "notes": ""})
    client.post("/logout")

    # Nurse sees the queue and records an abnormal result.
    _login(client, "nurse@example.com")
    queue = client.get("/clinical/labs/queue")
    assert queue.status_code == 200
    assert "CBC" in queue.text

    oid = _order_id(db_sessionmaker)
    resp = client.post(
        f"/clinical/labs/{oid}/results",
        data={"analyte": "Hemoglobin", "value": "8.0", "unit": "g/dL",
              "reference_low": "12.0", "reference_high": "17.0"},
    )
    assert resp.status_code == 200
    assert "abnormal" in resp.text.lower()


def test_patient_views_own_labs(
    client: TestClient, world: dict[str, int], db_sessionmaker: sessionmaker[Session]
) -> None:
    _login(client, "doc@example.com")
    client.post(f"/clinical/encounters/{world['enc']}/labs",
                data={"test_code": "CBC", "test_name": "Complete Blood Count", "notes": ""})
    client.post("/logout")

    _login(client, "pat@example.com")
    resp = client.get("/clinical/labs")
    assert resp.status_code == 200
    assert "Complete Blood Count" in resp.text


def test_non_nurse_cannot_see_queue(client: TestClient, world: dict[str, int]) -> None:
    _login(client, "doc@example.com")
    assert client.get("/clinical/labs/queue").status_code == 403
