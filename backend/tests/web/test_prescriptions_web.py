"""Web-layer tests for the prescribe flow (app.web.clinical prescriptions)."""

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
        s.add(amox)
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
        return {"doc": doc.id, "pat": pat.id, "amox": amox.id, "enc": enc.id}


def _login(client: TestClient, email: str) -> None:
    client.post("/login", data={"email": email, "password": PW})


def test_doctor_prescribes_via_htmx(client: TestClient, world: dict[str, int]) -> None:
    _login(client, "doc@example.com")
    resp = client.post(
        f"/clinical/encounters/{world['enc']}/prescriptions",
        data={"medication_id": world["amox"], "dose": "500mg", "refills": 1},
    )
    assert resp.status_code == 200
    assert "Amoxicillin" in resp.text
    assert "<html" not in resp.text.lower()  # partial


def test_allergy_block_shows_error_partial(
    client: TestClient, world: dict[str, int], db_sessionmaker: sessionmaker[Session]
) -> None:
    with db_sessionmaker() as s:
        s.add(Allergy(patient_id=world["pat"], substance="penicillin"))
        s.commit()
    _login(client, "doc@example.com")
    resp = client.post(
        f"/clinical/encounters/{world['enc']}/prescriptions",
        data={"medication_id": world["amox"], "dose": "500mg"},
    )
    assert resp.status_code == 409
    assert "form-error" in resp.text


def test_patient_prescriptions_page(client: TestClient, world: dict[str, int]) -> None:
    # Doctor prescribes, then patient views their list.
    _login(client, "doc@example.com")
    client.post(
        f"/clinical/encounters/{world['enc']}/prescriptions",
        data={"medication_id": world["amox"], "dose": "500mg"},
    )
    client.post("/logout")
    _login(client, "pat@example.com")
    resp = client.get("/clinical/prescriptions")
    assert resp.status_code == 200
    assert "Amoxicillin" in resp.text
