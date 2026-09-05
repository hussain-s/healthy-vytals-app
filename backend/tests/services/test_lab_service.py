"""Tests for the lab service (app.services.lab_service)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import PermissionDenied
from app.core.roles import Role
from app.domain.appointment_state import AppointmentStatus
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.clinical import Encounter
from app.models.scheduling import Appointment, AvailabilitySlot
from app.models.user import User
from app.services import lab_service

BASE = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s
    engine.dispose()


def _encounter(session: Session):
    doc = User(email="doc@example.com", password_hash="h", role=Role.DOCTOR)
    nurse = User(email="nurse@example.com", password_hash="h", role=Role.NURSE)
    pat = User(email="pat@example.com", password_hash="h", role=Role.PATIENT)
    session.add_all([doc, nurse, pat])
    session.flush()
    slot = AvailabilitySlot(doctor_id=doc.id, start_at=BASE, end_at=BASE + timedelta(minutes=30))
    session.add(slot)
    session.flush()
    appt = Appointment(patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id,
                       status=AppointmentStatus.IN_PROGRESS)
    session.add(appt)
    session.flush()
    enc = Encounter(appointment_id=appt.id, patient_id=pat.id, doctor_id=doc.id, opened_at=BASE)
    session.add(enc)
    session.flush()
    return enc, doc, nurse, pat


def test_order_lab_requires_owning_doctor(session: Session) -> None:
    enc, doc, nurse, pat = _encounter(session)
    other = User(email="doc2@example.com", password_hash="h", role=Role.DOCTOR)
    session.add(other)
    session.flush()
    with pytest.raises(PermissionDenied):
        lab_service.order_lab(session, other.id, enc.id, "CBC", "Complete Blood Count")
    order = lab_service.order_lab(session, doc.id, enc.id, "CBC", "Complete Blood Count")
    assert order.status == "ordered"


def test_record_result_flags_abnormal_and_resulted(session: Session) -> None:
    enc, doc, nurse, pat = _encounter(session)
    order = lab_service.order_lab(session, doc.id, enc.id, "CBC", "Complete Blood Count")
    result = lab_service.record_result(
        session, nurse.id, Role.NURSE, order.id, "Hemoglobin", 8.0, "g/dL", 12.0, 17.0
    )
    assert result.abnormal is True                       # 8.0 < 12.0
    assert session.get(type(order), order.id).status == "resulted"
    assert session.scalars(select(AuditLog).where(AuditLog.action == "lab.result")).all()


def test_record_result_normal_not_flagged(session: Session) -> None:
    enc, doc, nurse, pat = _encounter(session)
    order = lab_service.order_lab(session, doc.id, enc.id, "CBC", "CBC")
    result = lab_service.record_result(
        session, nurse.id, Role.NURSE, order.id, "WBC", 7.0, "10^9/L", 4.0, 11.0
    )
    assert result.abnormal is False


def test_patient_cannot_record_result(session: Session) -> None:
    enc, doc, nurse, pat = _encounter(session)
    order = lab_service.order_lab(session, doc.id, enc.id, "CBC", "CBC")
    with pytest.raises(PermissionDenied):
        lab_service.record_result(session, pat.id, Role.PATIENT, order.id, "WBC", 7.0)


def test_get_patient_labs_scoping(session: Session) -> None:
    enc, doc, nurse, pat = _encounter(session)
    order = lab_service.order_lab(session, doc.id, enc.id, "CBC", "CBC")
    lab_service.record_result(session, nurse.id, Role.NURSE, order.id, "WBC", 7.0, "x", 4.0, 11.0)

    # Patient sees own; treating doctor sees; non-treating doctor denied + audited.
    assert len(lab_service.get_patient_labs(session, pat.id, Role.PATIENT, pat.id)) == 1
    assert len(lab_service.get_patient_labs(session, doc.id, Role.DOCTOR, pat.id)) == 1

    other = User(email="doc2@example.com", password_hash="h", role=Role.DOCTOR)
    session.add(other)
    session.flush()
    with pytest.raises(PermissionDenied):
        lab_service.get_patient_labs(session, other.id, Role.DOCTOR, pat.id)
    assert session.scalars(select(AuditLog).where(AuditLog.action == "lab.read_denied")).all()
