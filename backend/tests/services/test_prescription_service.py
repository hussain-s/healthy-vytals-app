"""Tests for the prescription service (app.services.prescription_service)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.domain.appointment_state import AppointmentStatus
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.clinical import Encounter
from app.models.prescription import Allergy, DrugInteraction, Medication, Prescription
from app.models.scheduling import Appointment, AvailabilitySlot
from app.models.user import User
from app.services import prescription_service

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


def _med(session: Session, name: str, drug_class: str | None = None, controlled: bool = False) -> Medication:
    med = Medication(name=name, drug_class=drug_class, is_controlled=controlled)
    session.add(med)
    session.flush()
    return med


def test_clean_prescription_succeeds_and_audits(session: Session) -> None:
    enc = _encounter(session)
    med = _med(session, "Amoxicillin", "penicillin")
    rx = prescription_service.prescribe(session, enc.doctor_id, enc.id, med.id, "500mg", 2)
    assert rx.id is not None
    assert session.scalars(select(AuditLog).where(AuditLog.action == "prescription.create")).all()


def test_allergy_blocks_and_audits(session: Session) -> None:
    enc = _encounter(session)
    med = _med(session, "Amoxicillin", "penicillin")
    session.add(Allergy(patient_id=enc.patient_id, substance="penicillin"))
    session.flush()

    with pytest.raises(prescription_service.UnsafePrescription) as exc:
        prescription_service.prescribe(session, enc.doctor_id, enc.id, med.id, "500mg", 0)
    assert exc.value.details["reason"] == "allergy"
    assert session.scalars(select(AuditLog).where(AuditLog.action == "prescription.blocked")).all()


def test_controlled_refill_cap_blocks(session: Session) -> None:
    enc = _encounter(session)
    med = _med(session, "Oxycodone", "opioid", controlled=True)
    with pytest.raises(prescription_service.UnsafePrescription) as exc:
        prescription_service.prescribe(session, enc.doctor_id, enc.id, med.id, "5mg", 3)
    assert exc.value.details["reason"] == "refill_cap"


def test_interaction_blocks_then_override_succeeds(session: Session) -> None:
    enc = _encounter(session)
    a = _med(session, "DrugA")
    b = _med(session, "DrugB")
    session.add(DrugInteraction(medication_a_id=a.id, medication_b_id=b.id, severity="severe"))
    session.flush()
    # Patient already takes DrugA (active prescription).
    session.add(Prescription(encounter_id=enc.id, patient_id=enc.patient_id,
                             prescriber_id=enc.doctor_id, medication_id=a.id, dose="1", status="active"))
    session.flush()

    # Prescribing DrugB without override is blocked.
    with pytest.raises(prescription_service.UnsafePrescription) as exc:
        prescription_service.prescribe(session, enc.doctor_id, enc.id, b.id, "1", 0)
    assert exc.value.details["reason"] == "interaction"

    # With override it succeeds.
    rx = prescription_service.prescribe(
        session, enc.doctor_id, enc.id, b.id, "1", 0, override_interaction=True
    )
    assert rx.id is not None


def test_wrong_doctor_cannot_prescribe(session: Session) -> None:
    enc = _encounter(session)
    med = _med(session, "Amoxicillin")
    other = User(email="doc2@example.com", password_hash="h", role=Role.DOCTOR)
    session.add(other)
    session.flush()
    from app.core.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied):
        prescription_service.prescribe(session, other.id, enc.id, med.id, "500mg", 0)
