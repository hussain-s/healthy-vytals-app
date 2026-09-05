"""Concurrency guard for the 'last slot' booking race (DESIGN §5.2).

The booking service checks ``is_booked`` before creating an appointment, but two
concurrent transactions could both read ``is_booked == False`` before either
commits. The unique constraint on ``appointments.slot_id`` is the last line of
defense: at most one of the racing inserts can succeed; the other fails with an
IntegrityError, which the caller's transaction turns into a rollback.

This test simulates the race deterministically by driving two independent
sessions against one shared database and interleaving them so both pass the
``is_booked`` check before either commits.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.roles import Role
from app.domain.appointment_state import AppointmentStatus
from app.models.base import Base
from app.models.scheduling import Appointment, AvailabilitySlot
from app.models.user import User

BASE = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def sf() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False, future=True)
    engine.dispose()


def test_unique_slot_constraint_wins_the_race(sf: sessionmaker[Session]) -> None:
    # Arrange: a doctor, two patients, one open slot.
    with sf() as setup:
        doc = User(email="doc@example.com", password_hash="h", role=Role.DOCTOR)
        p1 = User(email="p1@example.com", password_hash="h", role=Role.PATIENT)
        p2 = User(email="p2@example.com", password_hash="h", role=Role.PATIENT)
        setup.add_all([doc, p1, p2])
        setup.flush()
        slot = AvailabilitySlot(doctor_id=doc.id, start_at=BASE, end_at=BASE + timedelta(minutes=30))
        setup.add(slot)
        setup.commit()
        slot_id, doc_id, p1_id, p2_id = slot.id, doc.id, p1.id, p2.id

    # Two independent sessions both create an appointment for the same slot,
    # simulating two requests that both passed the is_booked check.
    s1, s2 = sf(), sf()
    try:
        s1.add(
            Appointment(
                patient_id=p1_id, doctor_id=doc_id, slot_id=slot_id,
                status=AppointmentStatus.REQUESTED,
            )
        )
        s2.add(
            Appointment(
                patient_id=p2_id, doctor_id=doc_id, slot_id=slot_id,
                status=AppointmentStatus.REQUESTED,
            )
        )
        # First writer wins.
        s1.commit()
        # Second writer violates the unique(slot_id) constraint.
        with pytest.raises(IntegrityError):
            s2.commit()
        s2.rollback()
    finally:
        s1.close()
        s2.close()

    # Exactly one appointment exists for the slot.
    with sf() as verify:
        count = verify.scalar(
            select(func.count()).select_from(Appointment).where(Appointment.slot_id == slot_id)
        )
    assert count == 1
