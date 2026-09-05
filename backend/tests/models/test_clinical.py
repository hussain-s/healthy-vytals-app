"""Tests for clinical models (app.models.clinical): Encounter + Addendum."""

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
from app.models.clinical import Addendum, Diagnosis, Encounter, Vitals
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


def _appointment(session: Session) -> Appointment:
    doc = User(email="doc@example.com", password_hash="h", role=Role.DOCTOR)
    pat = User(email="pat@example.com", password_hash="h", role=Role.PATIENT)
    session.add_all([doc, pat])
    session.flush()
    slot = AvailabilitySlot(doctor_id=doc.id, start_at=BASE, end_at=BASE + timedelta(minutes=30))
    session.add(slot)
    session.flush()
    appt = Appointment(
        patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id, status=AppointmentStatus.IN_PROGRESS
    )
    session.add(appt)
    session.flush()
    return appt


def test_encounter_persists_and_defaults_open(session: Session) -> None:
    appt = _appointment(session)
    enc = Encounter(
        appointment_id=appt.id,
        patient_id=appt.patient_id,
        doctor_id=appt.doctor_id,
        opened_at=BASE,
    )
    session.add(enc)
    session.commit()

    stored = session.scalar(select(Encounter))
    assert stored.id is not None
    assert stored.closed_at is None  # open until documented


def test_one_encounter_per_appointment(session: Session) -> None:
    appt = _appointment(session)
    session.add(
        Encounter(appointment_id=appt.id, patient_id=appt.patient_id, doctor_id=appt.doctor_id, opened_at=BASE)
    )
    session.commit()
    session.add(
        Encounter(appointment_id=appt.id, patient_id=appt.patient_id, doctor_id=appt.doctor_id, opened_at=BASE)
    )
    with pytest.raises(IntegrityError):
        session.commit()


def _encounter(session: Session) -> Encounter:
    appt = _appointment(session)
    enc = Encounter(
        appointment_id=appt.id, patient_id=appt.patient_id, doctor_id=appt.doctor_id, opened_at=BASE
    )
    session.add(enc)
    session.flush()
    return enc


def test_vitals_persist_with_flags_default_empty(session: Session) -> None:
    enc = _encounter(session)
    v = Vitals(encounter_id=enc.id, recorded_by=enc.doctor_id, heart_rate=72, spo2=98)
    session.add(v)
    session.commit()
    stored = session.scalar(select(Vitals))
    assert stored.heart_rate == 72
    assert stored.flags == ""  # server_default


def test_diagnosis_persists(session: Session) -> None:
    enc = _encounter(session)
    d = Diagnosis(encounter_id=enc.id, author_id=enc.doctor_id, icd_code="J06.9", description="URI")
    session.add(d)
    session.commit()
    stored = session.scalar(select(Diagnosis))
    assert stored.icd_code == "J06.9"
    assert stored.description == "URI"


def test_addendum_references_target(session: Session) -> None:
    doc = User(email="doc@example.com", password_hash="h", role=Role.DOCTOR)
    session.add(doc)
    session.flush()
    add = Addendum(target_type="diagnosis", target_id=42, author_id=doc.id, note="correction")
    session.add(add)
    session.commit()

    stored = session.scalar(select(Addendum))
    assert stored.target_type == "diagnosis"
    assert stored.target_id == 42
    assert stored.note == "correction"
