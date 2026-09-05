"""API tests for slot publishing/listing (app.api.v1.appointments).

Exercises the doctor-only slot endpoints end to end via the shared client fixture.
Doctors are provisioned by an admin (staff are not self-service).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.models.user import User

PW = "longenough1"
START = "2026-09-01T09:00:00+00:00"
END = "2026-09-01T09:30:00+00:00"


@pytest.fixture
def doctor_token(client: TestClient, db_sessionmaker: sessionmaker[Session]) -> str:
    with db_sessionmaker() as s:
        s.add(User(email="doc@example.com", password_hash=hash_password(PW), role=Role.DOCTOR))
        s.commit()
    return client.post(
        "/api/v1/auth/login", json={"email": "doc@example.com", "password": PW}
    ).json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_doctor_publishes_and_lists_slot(client: TestClient, doctor_token: str) -> None:
    created = client.post(
        "/api/v1/appointments/slots",
        headers=_auth(doctor_token),
        json={"start_at": START, "end_at": END},
    )
    assert created.status_code == 201
    assert created.json()["is_booked"] is False

    mine = client.get("/api/v1/appointments/slots/mine", headers=_auth(doctor_token))
    assert mine.status_code == 200
    assert len(mine.json()) == 1


def test_publish_rejects_bad_interval(client: TestClient, doctor_token: str) -> None:
    resp = client.post(
        "/api/v1/appointments/slots",
        headers=_auth(doctor_token),
        json={"start_at": START, "end_at": START},
    )
    assert resp.status_code == 422  # schema validator rejects end<=start


def test_patient_cannot_publish_slot(client: TestClient) -> None:
    client.post("/api/v1/auth/register", json={"email": "pat@example.com", "password": PW})
    token = client.post(
        "/api/v1/auth/login", json={"email": "pat@example.com", "password": PW}
    ).json()["access_token"]

    resp = client.post(
        "/api/v1/appointments/slots",
        headers=_auth(token),
        json={"start_at": START, "end_at": END},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "permission_denied"


def test_patient_can_list_doctor_open_slots(
    client: TestClient, doctor_token: str, db_sessionmaker: sessionmaker[Session]
) -> None:
    # Doctor publishes a slot.
    client.post(
        "/api/v1/appointments/slots",
        headers=_auth(doctor_token),
        json={"start_at": START, "end_at": END},
    )
    # Find the doctor's id.
    with db_sessionmaker() as s:
        from sqlalchemy import select

        doctor_id = s.scalar(select(User.id).where(User.email == "doc@example.com"))

    client.post("/api/v1/auth/register", json={"email": "pat@example.com", "password": PW})
    token = client.post(
        "/api/v1/auth/login", json={"email": "pat@example.com", "password": PW}
    ).json()["access_token"]

    resp = client.get(
        f"/api/v1/appointments/slots/open/{doctor_id}", headers=_auth(token)
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_slot_endpoints_require_auth(client: TestClient) -> None:
    assert client.get("/api/v1/appointments/slots/mine").status_code == 401


def _publish_slot(client: TestClient, doctor_token: str) -> int:
    """Publish a slot and return the doctor's id (for open-slot listing)."""
    client.post(
        "/api/v1/appointments/slots",
        headers=_auth(doctor_token),
        json={"start_at": START, "end_at": END},
    )
    me = client.get("/api/v1/auth/me", headers=_auth(doctor_token))
    return me.json()["id"]


def _patient_token(client: TestClient) -> str:
    client.post("/api/v1/auth/register", json={"email": "pat@example.com", "password": PW})
    return client.post(
        "/api/v1/auth/login", json={"email": "pat@example.com", "password": PW}
    ).json()["access_token"]


def test_patient_books_open_slot(client: TestClient, doctor_token: str) -> None:
    doctor_id = _publish_slot(client, doctor_token)
    patient_token = _patient_token(client)
    open_slots = client.get(
        f"/api/v1/appointments/slots/open/{doctor_id}", headers=_auth(patient_token)
    ).json()
    slot_id = open_slots[0]["id"]

    booked = client.post(
        "/api/v1/appointments",
        headers=_auth(patient_token),
        json={"slot_id": slot_id, "reason": "cough"},
    )
    assert booked.status_code == 201
    assert booked.json()["status"] == "requested"

    # The slot is no longer open.
    remaining = client.get(
        f"/api/v1/appointments/slots/open/{doctor_id}", headers=_auth(patient_token)
    ).json()
    assert remaining == []

    # It shows up in the patient's appointments.
    mine = client.get("/api/v1/appointments/mine", headers=_auth(patient_token))
    assert len(mine.json()) == 1


def test_double_booking_returns_409(client: TestClient, doctor_token: str) -> None:
    doctor_id = _publish_slot(client, doctor_token)
    p1 = _patient_token(client)
    slot_id = client.get(
        f"/api/v1/appointments/slots/open/{doctor_id}", headers=_auth(p1)
    ).json()[0]["id"]

    assert client.post(
        "/api/v1/appointments", headers=_auth(p1), json={"slot_id": slot_id}
    ).status_code == 201

    # A second patient tries the same slot.
    client.post("/api/v1/auth/register", json={"email": "pat2@example.com", "password": PW})
    p2 = client.post(
        "/api/v1/auth/login", json={"email": "pat2@example.com", "password": PW}
    ).json()["access_token"]
    conflict = client.post(
        "/api/v1/appointments", headers=_auth(p2), json={"slot_id": slot_id}
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "slot_conflict"


def test_doctor_cannot_book(client: TestClient, doctor_token: str) -> None:
    """Booking is a patient action; a doctor is 403."""
    doctor_id = _publish_slot(client, doctor_token)
    resp = client.post(
        "/api/v1/appointments", headers=_auth(doctor_token), json={"slot_id": 1}
    )
    assert resp.status_code == 403


def _book_one(client: TestClient, doctor_token: str) -> tuple[int, str]:
    """Publish a slot, have a patient book it; return (appointment_id, patient_token)."""
    doctor_id = _publish_slot(client, doctor_token)
    patient_token = _patient_token(client)
    slot_id = client.get(
        f"/api/v1/appointments/slots/open/{doctor_id}", headers=_auth(patient_token)
    ).json()[0]["id"]
    appt = client.post(
        "/api/v1/appointments", headers=_auth(patient_token), json={"slot_id": slot_id}
    ).json()
    return appt["id"], patient_token


def test_doctor_confirms_then_patient_cancels(client: TestClient, doctor_token: str) -> None:
    appt_id, patient_token = _book_one(client, doctor_token)

    confirmed = client.post(
        f"/api/v1/appointments/{appt_id}/transitions/confirm", headers=_auth(doctor_token)
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    cancelled = client.post(
        f"/api/v1/appointments/{appt_id}/transitions/cancel", headers=_auth(patient_token)
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_illegal_transition_returns_409(client: TestClient, doctor_token: str) -> None:
    appt_id, _ = _book_one(client, doctor_token)
    # begin from requested is illegal.
    resp = client.post(
        f"/api/v1/appointments/{appt_id}/transitions/begin", headers=_auth(doctor_token)
    )
    assert resp.status_code == 409
    assert resp.json()["code"] == "illegal_transition"


def test_patient_cannot_confirm(client: TestClient, doctor_token: str) -> None:
    """Confirm is a doctor action; a patient attempting it is a 409 illegal transition."""
    appt_id, patient_token = _book_one(client, doctor_token)
    resp = client.post(
        f"/api/v1/appointments/{appt_id}/transitions/confirm", headers=_auth(patient_token)
    )
    assert resp.status_code == 409


def test_unknown_transition_is_422(client: TestClient, doctor_token: str) -> None:
    appt_id, _ = _book_one(client, doctor_token)
    resp = client.post(
        f"/api/v1/appointments/{appt_id}/transitions/teleport", headers=_auth(doctor_token)
    )
    assert resp.status_code == 422


def test_doctor_calendar_lists_their_appointments(client: TestClient, doctor_token: str) -> None:
    _book_one(client, doctor_token)
    resp = client.get("/api/v1/appointments/doctor", headers=_auth(doctor_token))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_ward_schedule_requires_nurse(
    client: TestClient, doctor_token: str, db_sessionmaker: sessionmaker[Session]
) -> None:
    _book_one(client, doctor_token)

    # A doctor is not a nurse → 403 on the ward view.
    assert client.get("/api/v1/appointments/ward", headers=_auth(doctor_token)).status_code == 403

    # Provision a nurse and confirm they can read the ward schedule.
    with db_sessionmaker() as s:
        s.add(User(email="nurse@example.com", password_hash=hash_password(PW), role=Role.NURSE))
        s.commit()
    nurse_token = client.post(
        "/api/v1/auth/login", json={"email": "nurse@example.com", "password": PW}
    ).json()["access_token"]
    ward = client.get("/api/v1/appointments/ward", headers=_auth(nurse_token))
    assert ward.status_code == 200
    assert len(ward.json()) == 1
