"""Tests for prescription-domain models (app.models.prescription)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.domain.appointment_state import AppointmentStatus
from app.models.base import Base
from app.models.clinical import Encounter
from app.models.prescription import (
    Allergy,
    DrugInteraction,
    Medication,
    Prescription,
)
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


def test_medication_defaults_not_controlled(session: Session) -> None:
    med = Medication(name="Amoxicillin", drug_class="penicillin")
    session.add(med)
    session.commit()
    stored = session.scalar(select(Medication))
    assert stored.is_controlled is False


def test_medication_name_unique(session: Session) -> None:
    session.add(Medication(name="Aspirin"))
    session.commit()
    session.add(Medication(name="Aspirin"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_allergy_records_substance(session: Session) -> None:
    pat = User(email="pat@example.com", password_hash="h", role=Role.PATIENT)
    session.add(pat)
    session.flush()
    session.add(Allergy(patient_id=pat.id, substance="penicillin", severity="severe"))
    session.commit()
    assert session.scalar(select(Allergy)).substance == "penicillin"


def test_interaction_pair_unique(session: Session) -> None:
    a = Medication(name="DrugA")
    b = Medication(name="DrugB")
    session.add_all([a, b])
    session.flush()
    session.add(DrugInteraction(medication_a_id=a.id, medication_b_id=b.id, severity="severe"))
    session.commit()
    session.add(DrugInteraction(medication_a_id=a.id, medication_b_id=b.id, severity="moderate"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_prescription_defaults(session: Session) -> None:
    doc = User(email="doc@example.com", password_hash="h", role=Role.DOCTOR)
    pat = User(email="pat@example.com", password_hash="h", role=Role.PATIENT)
    med = Medication(name="Amoxicillin")
    session.add_all([doc, pat, med])
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

    rx = Prescription(
        encounter_id=enc.id, patient_id=pat.id, prescriber_id=doc.id,
        medication_id=med.id, dose="500mg TID",
    )
    session.add(rx)
    session.commit()
    stored = session.scalar(select(Prescription))
    assert stored.refills == 0
    assert stored.status == "active"
