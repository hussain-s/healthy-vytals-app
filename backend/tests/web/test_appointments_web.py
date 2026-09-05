"""Web-layer tests for the patient booking flow (app.web.appointments).

Drives the server-rendered/HTMX screens via the shared client fixture: a patient
sees a doctor's open slots, books one (HTMX partial), sees it in their list, and
staff are kept out of the patient-only booking page.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.models.scheduling import AvailabilitySlot
from app.models.user import User

PW = "longenough1"
BASE = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def doctor_with_slot(db_sessionmaker: sessionmaker[Session]) -> int:
    """Create a doctor with one open slot; return the slot id."""
    with db_sessionmaker() as s:
        doc = User(email="doc@example.com", password_hash=hash_password(PW), role=Role.DOCTOR)
        s.add(doc)
        s.flush()
        slot = AvailabilitySlot(
            doctor_id=doc.id, start_at=BASE, end_at=BASE + timedelta(minutes=30)
        )
        s.add(slot)
        s.commit()
        return slot.id


def _login_patient(client: TestClient) -> None:
    client.post("/register", data={"email": "pat@example.com", "password": PW})


def test_book_page_lists_doctor_slots(client: TestClient, doctor_with_slot: int) -> None:
    _login_patient(client)
    resp = client.get("/appointments/book")
    assert resp.status_code == 200
    assert "doc@example.com" in resp.text
    assert "Book" in resp.text


def test_htmx_book_returns_confirmation_partial(
    client: TestClient, doctor_with_slot: int
) -> None:
    _login_patient(client)
    resp = client.post(
        "/appointments/book",
        data={"slot_id": doctor_with_slot, "reason": "cough"},
    )
    assert resp.status_code == 200
    assert "Booked!" in resp.text
    # A partial, not a full page.
    assert "<html" not in resp.text.lower()

    # The appointment now appears in the patient's list.
    mine = client.get("/appointments/mine")
    assert mine.status_code == 200
    assert "requested" in mine.text


def test_booking_taken_slot_shows_error_partial(
    client: TestClient, doctor_with_slot: int
) -> None:
    _login_patient(client)
    # First booking succeeds.
    client.post("/appointments/book", data={"slot_id": doctor_with_slot})
    # Second attempt on the same slot returns the error partial with a 409.
    resp = client.post("/appointments/book", data={"slot_id": doctor_with_slot})
    assert resp.status_code == 409
    assert "form-error" in resp.text


def test_book_page_requires_login(client: TestClient) -> None:
    resp = client.get("/appointments/book", follow_redirects=False)
    assert resp.status_code == 303  # redirect to /login


def test_doctor_cannot_open_patient_booking_page(
    client: TestClient, db_sessionmaker: sessionmaker[Session]
) -> None:
    with db_sessionmaker() as s:
        s.add(User(email="doc2@example.com", password_hash=hash_password(PW), role=Role.DOCTOR))
        s.commit()
    client.post("/login", data={"email": "doc2@example.com", "password": PW})
    resp = client.get("/appointments/book")
    assert resp.status_code == 403
