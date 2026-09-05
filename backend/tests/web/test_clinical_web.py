"""Web-layer tests for clinical screens (app.web.clinical).

Patient history view and doctor encounter page (HTMX diagnosis add) over the
shared client fixture. Data is seeded directly, then an encounter is opened via
the service path used elsewhere.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.domain.appointment_state import AppointmentStatus
from app.models.clinical import Encounter
from app.models.profile import PatientProfile
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
        s.add(PatientProfile(user_id=pat.id, date_of_birth=date(1986, 1, 1)))
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
        return {"doc": doc.id, "pat": pat.id, "encounter": enc.id}


def _login(client: TestClient, email: str) -> None:
    client.post("/login", data={"email": email, "password": PW})


def test_patient_history_page(client: TestClient, world: dict[str, int]) -> None:
    _login(client, "pat@example.com")
    resp = client.get("/clinical/history")
    assert resp.status_code == 200
    assert f"Encounter #{world['encounter']}" in resp.text


def test_doctor_encounter_page_and_htmx_diagnosis(client: TestClient, world: dict[str, int]) -> None:
    _login(client, "doc@example.com")
    page = client.get(f"/clinical/encounters/{world['encounter']}")
    assert page.status_code == 200
    assert "Add a diagnosis" in page.text

    added = client.post(
        f"/clinical/encounters/{world['encounter']}/diagnoses",
        data={"icd_code": "J06.9", "description": "Acute URI"},
    )
    assert added.status_code == 200
    assert "J06.9" in added.text
    assert "<html" not in added.text.lower()  # partial


def test_non_owning_doctor_cannot_view_encounter(
    client: TestClient, world: dict[str, int], db_sessionmaker: sessionmaker[Session]
) -> None:
    with db_sessionmaker() as s:
        s.add(User(email="doc2@example.com", password_hash=hash_password(PW), role=Role.DOCTOR))
        s.commit()
    _login(client, "doc2@example.com")
    resp = client.get(f"/clinical/encounters/{world['encounter']}")
    assert resp.status_code == 403


def test_history_requires_login(client: TestClient) -> None:
    assert client.get("/clinical/history", follow_redirects=False).status_code == 303
