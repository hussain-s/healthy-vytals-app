"""Patient clinical-summary service (NEW feature) — a compact chart header.

Assembles a small read-only summary of a patient for staff: the number of
encounters on record, the patient's active prescriptions, and their most recent
vitals. Intended for the top of a patient chart so a clinician gets the gist at a
glance.

Orchestrates reads across repositories and audits the access (§5.7).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import NotFound
from app.repositories.encounter_repository import EncounterRepository
from app.repositories.prescription_repository import PrescriptionRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_service import record_audit


def get_patient_summary(
    session: Session, viewer_id: int, patient_id: int
) -> dict:
    """Return a compact clinical summary for ``patient_id``.

    Loads the patient (404 if missing), gathers counts + latest vitals, audits the
    read, and returns a plain dict the router maps to a response schema.
    """
    users = UserRepository(session)
    patient = users.get(patient_id)
    if patient is None:
        raise NotFound(f"No such patient: {patient_id}")

    encounters = EncounterRepository(session)
    history = encounters.list_for_patient(patient_id)
    latest_vitals = None
    for enc in history:
        vitals = encounters.vitals_for_encounter(enc.id)
        if vitals:
            latest_vitals = vitals[-1]

    active_rx = [
        r for r in PrescriptionRepository(session).list_for_patient(patient_id)
        if r.status == "active"
    ]

    record_audit(
        session,
        action="summary.read",
        actor_id=viewer_id,
        resource_type="patient_summary",
        patient_id=patient_id,
    )
    return {
        "patient_id": patient_id,
        "email": patient.email,
        "encounter_count": len(history),
        "active_prescription_count": len(active_rx),
        "latest_vitals": latest_vitals,
    }
