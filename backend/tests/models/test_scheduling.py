"""Tests for scheduling models (app.models.scheduling)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from sqlalchemy.exc import IntegrityError

from app.core.roles import Role
from app.domain.appointment_state import AppointmentStatus
from app.models.base import Base
from app.models.scheduling import Appointment, AvailabilitySlot
from app.models.user import User


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s
    engine.dispose()


def _doctor(session: Session) -> User:
    doc = User(email="doc@example.com", password_hash="h", role=Role.DOCTOR)
    session.add(doc)
    session.flush()
    return doc


def test_slot_persists_with_defaults(session: Session) -> None:
    doc = _doctor(session)
    start = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
    slot = AvailabilitySlot(doctor_id=doc.id, start_at=start, end_at=start + timedelta(minutes=30))
    session.add(slot)
    session.commit()

    stored = session.scalar(select(AvailabilitySlot))
    assert stored is not None
    assert stored.id is not None
    assert stored.is_booked is False  # server_default
    assert stored.doctor_id == doc.id


def test_multiple_slots_for_doctor(session: Session) -> None:
    doc = _doctor(session)
    base = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
    for i in range(3):
        session.add(
            AvailabilitySlot(
                doctor_id=doc.id,
                start_at=base + timedelta(hours=i),
                end_at=base + timedelta(hours=i, minutes=30),
            )
        )
    session.commit()

    slots = session.scalars(
        select(AvailabilitySlot).order_by(AvailabilitySlot.start_at)
    ).all()
    assert len(slots) == 3


def _patient(session: Session) -> User:
    pat = User(email="pat@example.com", password_hash="h", role=Role.PATIENT)
    session.add(pat)
    session.flush()
    return pat


def _slot(session: Session, doctor: User) -> AvailabilitySlot:
    start = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)
    slot = AvailabilitySlot(doctor_id=doctor.id, start_at=start, end_at=start + timedelta(minutes=30))
    session.add(slot)
    session.flush()
    return slot


def test_appointment_defaults_to_requested(session: Session) -> None:
    doc, pat = _doctor(session), _patient(session)
    slot = _slot(session, doc)
    appt = Appointment(patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id, reason="cough")
    session.add(appt)
    session.commit()

    stored = session.scalar(select(Appointment))
    assert stored.status is AppointmentStatus.REQUESTED  # server_default
    assert stored.cancelled_late is False
    assert stored.reason == "cough"


def test_status_round_trips_as_string_value(session: Session) -> None:
    doc, pat = _doctor(session), _patient(session)
    slot = _slot(session, doc)
    appt = Appointment(
        patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id, status=AppointmentStatus.CONFIRMED
    )
    session.add(appt)
    session.commit()

    raw = session.execute(select(Appointment.status)).scalar_one()
    assert raw == AppointmentStatus.CONFIRMED
    assert AppointmentStatus(raw) is AppointmentStatus.CONFIRMED


def test_slot_id_is_unique_across_appointments(session: Session) -> None:
    """A slot can back at most one appointment row (no double-booking)."""
    doc, pat = _doctor(session), _patient(session)
    slot = _slot(session, doc)
    session.add(Appointment(patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id))
    session.commit()

    session.add(Appointment(patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id))
    with pytest.raises(IntegrityError):
        session.commit()
