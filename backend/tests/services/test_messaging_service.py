"""Tests for the messaging service (app.services.messaging_service)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import PermissionDenied, ValidationError
from app.core.roles import Role
from app.domain.appointment_state import AppointmentStatus
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.notification import Notification
from app.models.scheduling import Appointment, AvailabilitySlot
from app.models.user import User
from app.services import messaging_service

BASE = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s
    engine.dispose()


def _world(session: Session):
    doc = User(email="doc@example.com", password_hash="h", role=Role.DOCTOR)
    nurse = User(email="nurse@example.com", password_hash="h", role=Role.NURSE)
    pat = User(email="pat@example.com", password_hash="h", role=Role.PATIENT)
    session.add_all([doc, nurse, pat])
    session.flush()
    # Give the doctor a treating relationship with the patient (an appointment).
    slot = AvailabilitySlot(doctor_id=doc.id, start_at=BASE, end_at=BASE + timedelta(minutes=30))
    session.add(slot)
    session.flush()
    session.add(Appointment(patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id,
                            status=AppointmentStatus.CONFIRMED))
    session.flush()
    return doc, nurse, pat


def test_patient_messages_treating_doctor_notifies_and_audits(session: Session) -> None:
    doc, nurse, pat = _world(session)
    msg = messaging_service.send_message(session, pat.id, Role.PATIENT, doc.id, "Hello doctor")
    assert msg.body == "Hello doctor"
    # Recipient (doctor) is notified.
    notes = session.scalars(select(Notification).where(Notification.user_id == doc.id)).all()
    assert len(notes) == 1 and notes[0].event_type == "message.received"
    # Audited.
    assert session.scalars(select(AuditLog).where(AuditLog.action == "message.send")).all()


def test_thread_is_reused_for_same_pair(session: Session) -> None:
    doc, nurse, pat = _world(session)
    m1 = messaging_service.send_message(session, pat.id, Role.PATIENT, doc.id, "First")
    m2 = messaging_service.send_message(session, doc.id, Role.DOCTOR, pat.id, "Reply")
    assert m1.thread_id == m2.thread_id
    threads = messaging_service.list_threads(session, pat.id)
    assert len(threads) == 1
    assert threads[0]["message_count"] == 2


def test_non_treating_doctor_cannot_message(session: Session) -> None:
    doc, nurse, pat = _world(session)
    other = User(email="doc2@example.com", password_hash="h", role=Role.DOCTOR)
    session.add(other)
    session.flush()
    with pytest.raises(PermissionDenied):
        messaging_service.send_message(session, other.id, Role.DOCTOR, pat.id, "hi")


def test_empty_body_rejected(session: Session) -> None:
    doc, nurse, pat = _world(session)
    with pytest.raises(ValidationError):
        messaging_service.send_message(session, pat.id, Role.PATIENT, doc.id, "   ")


def test_patient_to_patient_rejected(session: Session) -> None:
    doc, nurse, pat = _world(session)
    pat2 = User(email="pat2@example.com", password_hash="h", role=Role.PATIENT)
    session.add(pat2)
    session.flush()
    with pytest.raises(PermissionDenied):
        messaging_service.send_message(session, pat.id, Role.PATIENT, pat2.id, "hi")


def test_get_thread_denies_non_participant_and_audits(session: Session) -> None:
    doc, nurse, pat = _world(session)
    msg = messaging_service.send_message(session, pat.id, Role.PATIENT, doc.id, "Hello")
    intruder = User(email="x@example.com", password_hash="h", role=Role.NURSE)
    session.add(intruder)
    session.flush()
    with pytest.raises(PermissionDenied):
        messaging_service.get_thread(session, intruder.id, msg.thread_id)
    assert session.scalars(select(AuditLog).where(AuditLog.action == "message.read_denied")).all()

    # A participant can read it.
    data = messaging_service.get_thread(session, doc.id, msg.thread_id)
    assert len(data["messages"]) == 1
