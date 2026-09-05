"""Tests for appointment slot publishing (app.services.appointment_service)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import IllegalTransition, PermissionDenied, ValidationError
from app.core.roles import Role
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.scheduling import Appointment, AvailabilitySlot
from app.domain.appointment_state import AppointmentStatus, Transition
from app.models.user import User
from app.services import appointment_service

BASE = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s
    engine.dispose()


@pytest.fixture
def doctor(session: Session) -> User:
    doc = User(email="doc@example.com", password_hash="h", role=Role.DOCTOR)
    session.add(doc)
    session.flush()
    return doc


def test_publish_slot_persists_and_audits(session: Session, doctor: User) -> None:
    slot = appointment_service.publish_slot(
        session, doctor.id, BASE, BASE + timedelta(minutes=30)
    )
    assert slot.id is not None
    assert slot.is_booked is False
    audits = session.scalars(select(AuditLog).where(AuditLog.action == "slot.publish")).all()
    assert len(audits) == 1
    assert audits[0].actor_id == doctor.id


def test_publish_slot_rejects_bad_interval(session: Session, doctor: User) -> None:
    with pytest.raises(ValidationError):
        appointment_service.publish_slot(session, doctor.id, BASE, BASE)


def test_publish_slot_conflicts_with_existing_appointment(
    session: Session, doctor: User
) -> None:
    """Publishing over a booked commitment (within buffer) is rejected (§5.2)."""
    # Create a booked slot + active appointment 09:00–09:30.
    booked = AvailabilitySlot(
        doctor_id=doctor.id, start_at=BASE, end_at=BASE + timedelta(minutes=30), is_booked=True
    )
    session.add(booked)
    session.flush()
    patient = User(email="pat@example.com", password_hash="h", role=Role.PATIENT)
    session.add(patient)
    session.flush()
    session.add(
        Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            slot_id=booked.id,
            status=AppointmentStatus.CONFIRMED,
        )
    )
    session.flush()

    # A new slot 5 min after (inside the default 10-min buffer) must be rejected.
    with pytest.raises(ValidationError, match="conflicts"):
        appointment_service.publish_slot(
            session,
            doctor.id,
            BASE + timedelta(minutes=35),
            BASE + timedelta(minutes=65),
        )


def test_publish_slot_allows_non_conflicting_time(session: Session, doctor: User) -> None:
    appointment_service.publish_slot(session, doctor.id, BASE, BASE + timedelta(minutes=30))
    # Well clear of the first slot → allowed.
    later = appointment_service.publish_slot(
        session, doctor.id, BASE + timedelta(hours=2), BASE + timedelta(hours=2, minutes=30)
    )
    assert later.id is not None


@pytest.fixture
def patient(session: Session) -> User:
    pat = User(email="pat@example.com", password_hash="h", role=Role.PATIENT)
    session.add(pat)
    session.flush()
    return pat


def test_book_appointment_marks_slot_and_audits(
    session: Session, doctor: User, patient: User
) -> None:
    slot = appointment_service.publish_slot(session, doctor.id, BASE, BASE + timedelta(minutes=30))
    appt = appointment_service.book_appointment(session, patient.id, slot.id, "checkup")

    assert appt.status is AppointmentStatus.REQUESTED
    assert appt.doctor_id == doctor.id
    assert session.get(AvailabilitySlot, slot.id).is_booked is True
    audits = session.scalars(select(AuditLog).where(AuditLog.action == "appointment.book")).all()
    assert len(audits) == 1
    assert audits[0].patient_id == patient.id


def test_book_unknown_slot_raises_not_found(session: Session, patient: User) -> None:
    from app.core.exceptions import NotFound

    with pytest.raises(NotFound):
        appointment_service.book_appointment(session, patient.id, 999999, None)


def test_book_already_booked_slot_raises_conflict(
    session: Session, doctor: User, patient: User
) -> None:
    slot = appointment_service.publish_slot(session, doctor.id, BASE, BASE + timedelta(minutes=30))
    appointment_service.book_appointment(session, patient.id, slot.id, None)

    other = User(email="pat2@example.com", password_hash="h", role=Role.PATIENT)
    session.add(other)
    session.flush()
    with pytest.raises(appointment_service.SlotConflict):
        appointment_service.book_appointment(session, other.id, slot.id, None)


def _book(session: Session, doctor: User, patient: User, minutes_ahead: int = 60):
    """Publish a slot `minutes_ahead` from now and book it; return the appointment."""
    start = datetime.now(timezone.utc) + timedelta(minutes=minutes_ahead)
    slot = appointment_service.publish_slot(session, doctor.id, start, start + timedelta(minutes=30))
    return appointment_service.book_appointment(session, patient.id, slot.id, None), slot


def test_doctor_confirm_then_cancel_frees_slot(
    session: Session, doctor: User, patient: User
) -> None:
    appt, slot = _book(session, doctor, patient)
    appointment_service.change_status(session, doctor.id, Role.DOCTOR, appt.id, Transition.CONFIRM)
    assert appt.status is AppointmentStatus.CONFIRMED

    # Patient cancels their own → slot is freed.
    appointment_service.change_status(session, patient.id, Role.PATIENT, appt.id, Transition.CANCEL)
    assert appt.status is AppointmentStatus.CANCELLED
    assert session.get(AvailabilitySlot, slot.id).is_booked is False


def test_cancel_far_ahead_is_not_late(session: Session, doctor: User, patient: User) -> None:
    appt, _ = _book(session, doctor, patient, minutes_ahead=60 * 48)  # 48h ahead
    appointment_service.change_status(session, patient.id, Role.PATIENT, appt.id, Transition.CANCEL)
    assert appt.cancelled_late is False


def test_cancel_within_cutoff_is_flagged_late(
    session: Session, doctor: User, patient: User
) -> None:
    appt, _ = _book(session, doctor, patient, minutes_ahead=60)  # 1h ahead, cutoff 24h
    appointment_service.change_status(session, patient.id, Role.PATIENT, appt.id, Transition.CANCEL)
    assert appt.cancelled_late is True


def test_illegal_transition_raises(session: Session, doctor: User, patient: User) -> None:
    appt, _ = _book(session, doctor, patient)  # status = requested
    with pytest.raises(IllegalTransition):
        # Cannot begin an appointment that was only requested.
        appointment_service.change_status(session, doctor.id, Role.DOCTOR, appt.id, Transition.BEGIN)


def test_patient_cannot_transition_others_appointment(
    session: Session, doctor: User, patient: User
) -> None:
    appt, _ = _book(session, doctor, patient)
    other = User(email="pat3@example.com", password_hash="h", role=Role.PATIENT)
    session.add(other)
    session.flush()
    with pytest.raises(PermissionDenied):
        appointment_service.change_status(session, other.id, Role.PATIENT, appt.id, Transition.CANCEL)


def test_staff_advance_lifecycle(session: Session, doctor: User, patient: User) -> None:
    appt, _ = _book(session, doctor, patient)
    appointment_service.change_status(session, doctor.id, Role.DOCTOR, appt.id, Transition.CONFIRM)
    # Nurse checks in.
    nurse = User(email="nurse@example.com", password_hash="h", role=Role.NURSE)
    session.add(nurse)
    session.flush()
    appointment_service.change_status(session, nurse.id, Role.NURSE, appt.id, Transition.CHECK_IN)
    assert appt.status is AppointmentStatus.CHECKED_IN
    # Doctor begins + completes.
    appointment_service.change_status(session, doctor.id, Role.DOCTOR, appt.id, Transition.BEGIN)
    appointment_service.change_status(session, doctor.id, Role.DOCTOR, appt.id, Transition.COMPLETE)
    assert appt.status is AppointmentStatus.COMPLETED
