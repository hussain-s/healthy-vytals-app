"""Clinical service — encounters, vitals, diagnoses, history, and immutability.

Orchestrates the Phase 3 use cases, wiring the pure domain rules (vitals ranges
§5.5, treating-relationship scoping §5.3) to persistence and audit inside the
caller's unit of work. Enforces the append-only rule (§5.6): this service exposes
*create* and *addendum* operations only — there is no update/delete of clinical
records, by design.

Every PHI read/write here is audited (§5.7).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import NotFound, PermissionDenied
from app.core.roles import Role
from app.domain.access_scope import can_view_patient_history, is_encounter_visible
from app.domain.vitals_ranges import VitalsReading, flag_out_of_range
from app.models.clinical import Addendum, Diagnosis, Encounter, Vitals
from app.repositories.encounter_repository import EncounterRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_service import record_audit


def _age_years(dob: date | None, on: datetime) -> int:
    """Whole years from ``dob`` to ``on``; defaults to adult (40) when unknown.

    Age drives the vitals ranges (§5.5). If the patient has no recorded DOB we
    fall back to an adult band rather than guessing — documented so a reviewer
    knows it is intentional, not a bug.
    """
    if dob is None:
        return 40
    years = on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))
    return max(0, years)


def _ensure_encounter(session: Session, appointment_id: int, actor_id: int) -> Encounter:
    """Return the appointment's encounter, creating it if needed (append-only).

    The encounter is always attributed to the appointment's assigned doctor,
    regardless of who triggers creation — so a nurse recording triage vitals can
    bring the encounter into being without owning it. Audits encounter.open only
    when it actually creates one. Callers enforce their own role/ownership rules.
    """
    repo = EncounterRepository(session)
    existing = repo.get_by_appointment(appointment_id)
    if existing is not None:
        return existing

    from app.repositories.appointment_repository import AppointmentRepository

    appointment = AppointmentRepository(session).get(appointment_id)
    if appointment is None:
        raise NotFound(f"No such appointment: {appointment_id}")

    encounter = repo.add(
        Encounter(
            appointment_id=appointment_id,
            patient_id=appointment.patient_id,
            doctor_id=appointment.doctor_id,
            opened_at=datetime.now(timezone.utc),
        )
    )
    record_audit(
        session,
        action="encounter.open",
        actor_id=actor_id,
        resource_type="encounter",
        resource_id=encounter.id,
        patient_id=appointment.patient_id,
    )
    return encounter


def open_encounter(session: Session, doctor_id: int, appointment_id: int) -> Encounter:
    """Open (or return the existing) encounter for an appointment (story C2).

    Doctor-facing: the caller must be the appointment's assigned doctor. Idempotent
    (returns an existing encounter). Delegates creation to :func:`_ensure_encounter`.
    """
    from app.repositories.appointment_repository import AppointmentRepository

    appointment = AppointmentRepository(session).get(appointment_id)
    if appointment is None:
        raise NotFound(f"No such appointment: {appointment_id}")
    if appointment.doctor_id != doctor_id:
        raise PermissionDenied("You are not the doctor for this appointment")
    return _ensure_encounter(session, appointment_id, actor_id=doctor_id)


def record_vitals_for_appointment(
    session: Session, nurse_id: int, appointment_id: int, reading: VitalsReading
) -> Vitals:
    """Nurse triage: ensure the appointment's encounter exists, then record vitals.

    Models real triage — the nurse records vitals against the appointment before
    the doctor's consult. Reuses :func:`record_vitals` for the age-flagging + audit.
    """
    encounter = _ensure_encounter(session, appointment_id, actor_id=nurse_id)
    return record_vitals(session, nurse_id, encounter.id, reading)


def record_vitals(
    session: Session, nurse_id: int, encounter_id: int, reading: VitalsReading
) -> Vitals:
    """Record a nurse's vitals for an encounter, flagging out-of-range values (C1, §5.5).

    Computes the patient's age from their profile and runs the pure age-based rule
    to derive flags, stored with the reading. Audits vitals.record.
    """
    repo = EncounterRepository(session)
    encounter = repo.get(encounter_id)
    if encounter is None:
        raise NotFound(f"No such encounter: {encounter_id}")

    profile = UserRepository(session).get_patient_profile(encounter.patient_id)
    dob = profile.date_of_birth if profile is not None else None
    age = _age_years(dob, datetime.now(timezone.utc))
    flags = flag_out_of_range(age, reading)

    vitals = repo.add_vitals(
        Vitals(
            encounter_id=encounter_id,
            recorded_by=nurse_id,
            heart_rate=reading.heart_rate,
            resp_rate=reading.resp_rate,
            systolic_bp=reading.systolic_bp,
            temp_c=reading.temp_c,
            spo2=reading.spo2,
            flags=",".join(flags),
        )
    )
    record_audit(
        session,
        action="vitals.record",
        actor_id=nurse_id,
        resource_type="vitals",
        resource_id=vitals.id,
        patient_id=encounter.patient_id,
    )
    return vitals


def add_diagnosis(
    session: Session, doctor_id: int, encounter_id: int, icd_code: str, description: str
) -> Diagnosis:
    """Author a diagnosis on an encounter (story C2). Doctor-only, append-only.

    The doctor must be the one who owns the encounter. Audits diagnosis.create.
    """
    repo = EncounterRepository(session)
    encounter = repo.get(encounter_id)
    if encounter is None:
        raise NotFound(f"No such encounter: {encounter_id}")
    if encounter.doctor_id != doctor_id:
        raise PermissionDenied("Only the encounter's doctor may add a diagnosis")

    diagnosis = repo.add_diagnosis(
        Diagnosis(
            encounter_id=encounter_id,
            author_id=doctor_id,
            icd_code=icd_code,
            description=description,
        )
    )
    record_audit(
        session,
        action="diagnosis.create",
        actor_id=doctor_id,
        resource_type="diagnosis",
        resource_id=diagnosis.id,
        patient_id=encounter.patient_id,
    )
    return diagnosis


def add_addendum(
    session: Session,
    author_id: int,
    author_role: Role,
    target_type: str,
    target_id: int,
    note: str,
) -> Addendum:
    """Append an immutable correction to a clinical record (story C3, §5.6).

    Corrections are addenda, never edits. Only clinical staff (nurse/doctor) may
    author them. Audits addendum.create.
    """
    if author_role not in (Role.DOCTOR, Role.NURSE):
        raise PermissionDenied("Only clinical staff may add addenda")

    addendum = EncounterRepository(session).add_addendum(
        Addendum(target_type=target_type, target_id=target_id, author_id=author_id, note=note)
    )
    record_audit(
        session,
        action="addendum.create",
        actor_id=author_id,
        resource_type=target_type,
        resource_id=target_id,
    )
    return addendum


def get_patient_history(
    session: Session, viewer_id: int, viewer_role: Role, patient_id: int
) -> list[Encounter]:
    """Return a patient's encounters if the viewer is allowed (C4, C5; §5.3).

    Applies the treating-relationship scoping predicate: a doctor needs a treating
    relationship, a patient sees only their own, a nurse may read, admin may not.
    A denied access is audited (history.read_denied) and raises 403; an allowed
    read is audited (history.read).
    """
    repo = EncounterRepository(session)
    treating = (
        repo.has_treating_relationship(viewer_id, patient_id)
        if viewer_role is Role.DOCTOR
        else False
    )
    if not can_view_patient_history(viewer_role, viewer_id, patient_id, treating):
        record_audit(
            session,
            action="history.read_denied",
            actor_id=viewer_id,
            resource_type="patient_history",
            patient_id=patient_id,
            commit=True,
        )
        raise PermissionDenied("You may not view this patient's history")

    record_audit(
        session,
        action="history.read",
        actor_id=viewer_id,
        resource_type="patient_history",
        patient_id=patient_id,
    )
    # Apply the per-record consent gate (§5.8): sensitive encounters are hidden
    # from staff without shared consent; the patient always sees their own.
    return [
        e
        for e in repo.list_for_patient(patient_id)
        if is_encounter_visible(
            viewer_role,
            viewer_id,
            patient_id,
            sensitive=e.sensitive,
            consent_shared=e.consent_shared,
        )
    ]
