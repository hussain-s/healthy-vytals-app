"""Tests for lab models (app.models.lab): LabOrder + LabResult."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.domain.appointment_state import AppointmentStatus
from app.models.base import Base
from app.models.clinical import Encounter
from app.models.lab import LabOrder, LabResult
from app.models.scheduling import Appointment, AvailabilitySlot
from app.models.user import User

BASE = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s
    engine.dispose()


def _encounter(session: Session) -> Encounter:
    doc = User(email="doc@example.com", password_hash="h", role=Role.DOCTOR)
    pat = User(email="pat@example.com", password_hash="h", role=Role.PATIENT)
    session.add_all([doc, pat])
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
    return enc


def test_lab_order_defaults_to_ordered(session: Session) -> None:
    enc = _encounter(session)
    order = LabOrder(encounter_id=enc.id, patient_id=enc.patient_id, ordered_by=enc.doctor_id,
                     test_code="CBC", test_name="Complete Blood Count")
    session.add(order)
    session.commit()
    stored = session.scalar(select(LabOrder))
    assert stored.status == "ordered"
    assert stored.test_name == "Complete Blood Count"


def test_lab_order_accumulates_results(session: Session) -> None:
    enc = _encounter(session)
    order = LabOrder(encounter_id=enc.id, patient_id=enc.patient_id, ordered_by=enc.doctor_id,
                     test_code="CBC", test_name="Complete Blood Count")
    session.add(order)
    session.flush()
    session.add_all([
        LabResult(lab_order_id=order.id, recorded_by=enc.doctor_id, analyte="WBC",
                  value=7.0, unit="10^9/L", reference_low=4.0, reference_high=11.0, abnormal=False),
        LabResult(lab_order_id=order.id, recorded_by=enc.doctor_id, analyte="Hemoglobin",
                  value=8.0, unit="g/dL", reference_low=12.0, reference_high=17.0, abnormal=True),
    ])
    session.commit()
    results = session.scalars(select(LabResult).where(LabResult.lab_order_id == order.id)).all()
    assert len(results) == 2
    assert {r.abnormal for r in results} == {False, True}
