"""Database seed data entrypoint.

Running this module populates the database with representative demo data so a
fresh clone is immediately explorable. It is **idempotent**: it upserts by the
natural key (email for users), so running it repeatedly never creates duplicates.

Phase 1 seeds one account per role (patient, nurse, doctor, admin) plus their
profiles, all sharing a well-known demo password. Phase 4 adds a small curated
medication catalog + a drug-interaction pair so the prescribe flow is explorable.
Each section is independently idempotent (upsert by natural key).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.roles import Role
from app.core.security import hash_password
from app.db.session import unit_of_work
from app.domain.appointment_state import AppointmentStatus
from app.models.clinical import Diagnosis, Encounter, Vitals
from app.models.prescription import DrugInteraction, Medication, Prescription
from app.models.profile import DoctorProfile, NurseProfile, PatientProfile
from app.models.scheduling import Appointment, AvailabilitySlot
from app.models.user import User
from app.repositories.prescription_repository import MedicationRepository
from app.repositories.user_repository import UserRepository

# Shared password for every seeded demo account. Obviously not for real use — it
# exists so a newcomer can log in as any role immediately after setup.
DEMO_PASSWORD = "Passw0rd!"

# The demo accounts, one per role. (email, role, profile-kwargs).
_DEMO_USERS: list[tuple[str, Role, dict[str, object]]] = [
    ("patient@healthyvytals.example.com", Role.PATIENT, {"sex": "F", "phone": "555-0100"}),
    ("nurse@healthyvytals.example.com", Role.NURSE, {"ward": "General"}),
    ("doctor@healthyvytals.example.com", Role.DOCTOR, {"specialty": "Family Medicine", "license_no": "LIC-1001"}),
    ("admin@healthyvytals.example.com", Role.ADMIN, {}),
]

# Which profile model backs each role (ADMIN has none).
_PROFILE_BY_ROLE = {
    Role.PATIENT: PatientProfile,
    Role.DOCTOR: DoctorProfile,
    Role.NURSE: NurseProfile,
}

# Curated demo medication catalog: (name, drug_class, is_controlled).
_DEMO_MEDICATIONS: list[tuple[str, str | None, bool]] = [
    ("Amoxicillin", "penicillin", False),
    ("Ibuprofen", "nsaid", False),
    ("Warfarin", "anticoagulant", False),
    ("Aspirin", "nsaid", False),
    ("Oxycodone", "opioid", True),
]

# Curated interacting pairs by name (warfarin + an NSAID raises bleeding risk).
_DEMO_INTERACTIONS: list[tuple[str, str, str]] = [
    ("Warfarin", "Aspirin", "severe"),
    ("Warfarin", "Ibuprofen", "moderate"),
]


def _seed_users(session) -> int:
    users = UserRepository(session)
    created = 0
    for email, role, profile_kwargs in _DEMO_USERS:
        if users.email_exists(email):
            continue
        user = users.add(User(email=email, password_hash=hash_password(DEMO_PASSWORD), role=role))
        profile_cls = _PROFILE_BY_ROLE.get(role)
        if profile_cls is not None:
            session.add(profile_cls(user_id=user.id, **profile_kwargs))
        created += 1
    return created


def _seed_medications(session) -> int:
    meds = MedicationRepository(session)
    created = 0
    for name, drug_class, controlled in _DEMO_MEDICATIONS:
        if meds.get_by_name(name) is None:
            meds.add(Medication(name=name, drug_class=drug_class, is_controlled=controlled))
            created += 1
    return created


def _seed_interactions(session) -> int:
    meds = MedicationRepository(session)
    created = 0
    for name_a, name_b, severity in _DEMO_INTERACTIONS:
        a, b = meds.get_by_name(name_a), meds.get_by_name(name_b)
        if a is None or b is None:
            continue
        existing = session.scalar(
            select(DrugInteraction).where(
                DrugInteraction.medication_a_id == a.id,
                DrugInteraction.medication_b_id == b.id,
            )
        )
        if existing is None:
            session.add(DrugInteraction(medication_a_id=a.id, medication_b_id=b.id, severity=severity))
            created += 1
    return created


def _seed_clinical_journey(session) -> bool:
    """Create one complete demo journey so the app is explorable on first run.

    Books a completed appointment for the demo patient with the demo doctor, opens
    an encounter, records vitals + a diagnosis, and writes one prescription.
    Idempotent: keyed on the demo patient having any appointment already.
    """
    users = UserRepository(session)
    patient = users.get_by_email("patient@healthyvytals.example.com")
    doctor = users.get_by_email("doctor@healthyvytals.example.com")
    if patient is None or doctor is None:
        return False
    already = session.scalar(
        select(Appointment.id).where(Appointment.patient_id == patient.id).limit(1)
    )
    if already is not None:
        return False  # journey already seeded

    # Use a fixed base time so seeding is deterministic (no wall-clock reads here).
    base = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)
    slot = AvailabilitySlot(
        doctor_id=doctor.id, start_at=base, end_at=base + timedelta(minutes=30), is_booked=True
    )
    session.add(slot)
    session.flush()
    appt = Appointment(
        patient_id=patient.id, doctor_id=doctor.id, slot_id=slot.id,
        status=AppointmentStatus.COMPLETED, reason="Persistent cough",
    )
    session.add(appt)
    session.flush()
    enc = Encounter(
        appointment_id=appt.id, patient_id=patient.id, doctor_id=doctor.id,
        opened_at=base, closed_at=base + timedelta(minutes=25),
    )
    session.add(enc)
    session.flush()
    session.add(Vitals(
        encounter_id=enc.id, recorded_by=doctor.id,
        heart_rate=78, resp_rate=16, systolic_bp=122, temp_c=37.1, spo2=98, flags="",
    ))
    session.add(Diagnosis(
        encounter_id=enc.id, author_id=doctor.id, icd_code="J06.9",
        description="Acute upper respiratory infection",
    ))
    amox = MedicationRepository(session).get_by_name("Amoxicillin")
    if amox is not None:
        session.add(Prescription(
            encounter_id=enc.id, patient_id=patient.id, prescriber_id=doctor.id,
            medication_id=amox.id, dose="500mg TID", refills=1, status="active",
        ))
    return True


def seed() -> None:
    """Populate the database with demo users, meds, interactions, and one journey (idempotent)."""
    with unit_of_work() as session:
        users_created = _seed_users(session)
        session.flush()  # journey + interactions reference these ids
        meds_created = _seed_medications(session)
        session.flush()  # interactions + prescription need medication ids
        interactions_created = _seed_interactions(session)
        journey_created = _seed_clinical_journey(session)

    if users_created or meds_created or interactions_created or journey_created:
        print(
            f"Seed: created {users_created} user(s), {meds_created} medication(s), "
            f"{interactions_created} interaction(s), "
            f"{'1' if journey_created else '0'} clinical journey. Demo password: {DEMO_PASSWORD}"
        )
    else:
        print("Seed: demo data already present. Nothing to do.")


if __name__ == "__main__":
    seed()
