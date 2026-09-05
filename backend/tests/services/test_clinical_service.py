"""Tests for the clinical service (app.services.clinical_service)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import NotFound, PermissionDenied
from app.core.roles import Role
from app.domain.appointment_state import AppointmentStatus
from app.domain.vitals_ranges import VitalsReading
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.profile import PatientProfile
from app.models.scheduling import Appointment, AvailabilitySlot
from app.models.user import User
from app.services import clinical_service

BASE = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s
    engine.dispose()


def _setup(session: Session, patient_dob: date | None = None) -> tuple[User, User, Appointment]:
    doc = User(email="doc@example.com", password_hash="h", role=Role.DOCTOR)
    pat = User(email="pat@example.com", password_hash="h", role=Role.PATIENT)
    session.add_all([doc, pat])
    session.flush()
    session.add(PatientProfile(user_id=pat.id, date_of_birth=patient_dob))
    slot = AvailabilitySlot(doctor_id=doc.id, start_at=BASE, end_at=BASE + timedelta(minutes=30))
    session.add(slot)
    session.flush()
    appt = Appointment(patient_id=pat.id, doctor_id=doc.id, slot_id=slot.id,
                       status=AppointmentStatus.IN_PROGRESS)
    session.add(appt)
    session.flush()
    return doc, pat, appt


def test_open_encounter_is_idempotent(session: Session) -> None:
    doc, _, appt = _setup(session)
    e1 = clinical_service.open_encounter(session, doc.id, appt.id)
    e2 = clinical_service.open_encounter(session, doc.id, appt.id)
    assert e1.id == e2.id  # same encounter, not a duplicate


def test_open_encounter_wrong_doctor_denied(session: Session) -> None:
    _, _, appt = _setup(session)
    other = User(email="doc2@example.com", password_hash="h", role=Role.DOCTOR)
    session.add(other)
    session.flush()
    with pytest.raises(PermissionDenied):
        clinical_service.open_encounter(session, other.id, appt.id)


def test_record_vitals_flags_out_of_range_by_age(session: Session) -> None:
    """An adult with HR 150 is flagged; the age comes from the patient profile."""
    doc, pat, appt = _setup(session, patient_dob=date(1986, 1, 1))  # ~40y
    nurse = User(email="nurse@example.com", password_hash="h", role=Role.NURSE)
    session.add(nurse)
    session.flush()
    enc = clinical_service.open_encounter(session, doc.id, appt.id)

    vitals = clinical_service.record_vitals(
        session, nurse.id, enc.id, VitalsReading(heart_rate=150, spo2=98)
    )
    assert "heart_rate_high" in vitals.flags
    audits = session.scalars(select(AuditLog).where(AuditLog.action == "vitals.record")).all()
    assert len(audits) == 1


def test_add_diagnosis_requires_owning_doctor(session: Session) -> None:
    doc, _, appt = _setup(session)
    enc = clinical_service.open_encounter(session, doc.id, appt.id)
    other = User(email="doc2@example.com", password_hash="h", role=Role.DOCTOR)
    session.add(other)
    session.flush()
    with pytest.raises(PermissionDenied):
        clinical_service.add_diagnosis(session, other.id, enc.id, "J06.9", "URI")

    # Owning doctor succeeds.
    dx = clinical_service.add_diagnosis(session, doc.id, enc.id, "J06.9", "URI")
    assert dx.icd_code == "J06.9"


def test_history_scoping_allows_treating_doctor_denies_others(session: Session) -> None:
    doc, pat, appt = _setup(session)
    clinical_service.open_encounter(session, doc.id, appt.id)

    # Treating doctor can read.
    history = clinical_service.get_patient_history(session, doc.id, Role.DOCTOR, pat.id)
    assert len(history) == 1

    # A non-treating doctor is denied and the denial is audited.
    other = User(email="doc2@example.com", password_hash="h", role=Role.DOCTOR)
    session.add(other)
    session.flush()
    with pytest.raises(PermissionDenied):
        clinical_service.get_patient_history(session, other.id, Role.DOCTOR, pat.id)
    denials = session.scalars(
        select(AuditLog).where(AuditLog.action == "history.read_denied")
    ).all()
    assert len(denials) == 1


def test_patient_sees_only_own_history(session: Session) -> None:
    doc, pat, appt = _setup(session)
    clinical_service.open_encounter(session, doc.id, appt.id)
    # Patient reads own → ok.
    assert len(clinical_service.get_patient_history(session, pat.id, Role.PATIENT, pat.id)) == 1
    # Patient reads someone else → denied.
    with pytest.raises(PermissionDenied):
        clinical_service.get_patient_history(session, pat.id, Role.PATIENT, 99999)


def test_sensitive_encounter_hidden_from_staff_without_consent(session: Session) -> None:
    """A treating doctor sees the patient's non-sensitive encounters but not a
    sensitive one until consent is shared; the patient always sees their own."""
    doc, pat, appt = _setup(session)
    enc = clinical_service.open_encounter(session, doc.id, appt.id)
    enc.sensitive = True
    session.flush()

    # Treating doctor: sensitive encounter is filtered out (no consent).
    assert clinical_service.get_patient_history(session, doc.id, Role.DOCTOR, pat.id) == []
    # Patient sees their own regardless.
    assert len(clinical_service.get_patient_history(session, pat.id, Role.PATIENT, pat.id)) == 1

    # Once consent is shared, the doctor can see it.
    enc.consent_shared = True
    session.flush()
    assert len(clinical_service.get_patient_history(session, doc.id, Role.DOCTOR, pat.id)) == 1


def test_record_vitals_for_appointment_creates_encounter(session: Session) -> None:
    """Nurse triage records vitals against an appointment, creating its encounter."""
    doc, pat, appt = _setup(session, patient_dob=date(1986, 1, 1))
    nurse = User(email="nurse@example.com", password_hash="h", role=Role.NURSE)
    session.add(nurse)
    session.flush()

    # No encounter yet.
    from app.repositories.encounter_repository import EncounterRepository
    assert EncounterRepository(session).get_by_appointment(appt.id) is None

    vitals = clinical_service.record_vitals_for_appointment(
        session, nurse.id, appt.id, VitalsReading(heart_rate=150)
    )
    # Encounter created (attributed to the appointment's doctor) + vitals flagged.
    enc = EncounterRepository(session).get_by_appointment(appt.id)
    assert enc is not None
    assert enc.doctor_id == doc.id
    assert vitals.encounter_id == enc.id
    assert "heart_rate_high" in vitals.flags


def test_addendum_requires_clinical_staff(session: Session) -> None:
    doc, pat, _ = _setup(session)
    # Doctor can add.
    add = clinical_service.add_addendum(session, doc.id, Role.DOCTOR, "diagnosis", 1, "typo fix")
    assert add.id is not None
    # Patient cannot.
    with pytest.raises(PermissionDenied):
        clinical_service.add_addendum(session, pat.id, Role.PATIENT, "diagnosis", 1, "nope")
