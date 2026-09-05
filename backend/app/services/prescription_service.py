"""Prescription service — safety-checked prescribing and prescription reads.

Orchestrates the §5.4 safety rule: gathers the patient's allergy terms and
interacting active medications from repositories, runs the pure evaluator, and
either blocks with a typed error or creates the prescription — all in the caller's
unit of work, audited (§5.7).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import Conflict, NotFound, PermissionDenied
from app.domain.prescription_safety import (
    DrugFacts,
    SafetyContext,
    evaluate_prescription,
)
from app.models.prescription import Prescription
from app.repositories.encounter_repository import EncounterRepository
from app.repositories.prescription_repository import (
    MedicationRepository,
    PrescriptionRepository,
)
from app.services import notification_service
from app.services.audit_service import record_audit


class UnsafePrescription(Conflict):
    """A prescription was blocked by a §5.4 safety check.

    Carries the block reason (allergy | interaction | refill_cap) in ``details``
    so clients can branch (e.g. offer an override for interactions only).
    """

    code = "unsafe_prescription"


def prescribe(
    session: Session,
    doctor_id: int,
    encounter_id: int,
    medication_id: int,
    dose: str,
    refills: int,
    *,
    override_interaction: bool = False,
) -> Prescription:
    """Prescribe a medication after running the §5.4 safety checks (story D1).

    Steps (atomic in the caller's unit of work):
      1. Load encounter (404) and confirm the prescriber owns it (403).
      2. Load the medication (404).
      3. Gather safety facts (allergy terms, interacting active meds) and run the
         pure evaluator.
      4. If blocked, audit prescription.blocked (committed, survives the raise)
         and raise UnsafePrescription with the reason.
      5. Otherwise create the prescription and audit prescription.create (with any
         non-blocking warnings noted).
    """
    encounters = EncounterRepository(session)
    encounter = encounters.get(encounter_id)
    if encounter is None:
        raise NotFound(f"No such encounter: {encounter_id}")
    if encounter.doctor_id != doctor_id:
        raise PermissionDenied("Only the encounter's doctor may prescribe")

    meds = MedicationRepository(session)
    medication = meds.get(medication_id)
    if medication is None:
        raise NotFound(f"No such medication: {medication_id}")

    rx_repo = PrescriptionRepository(session)
    context = SafetyContext(
        allergy_terms=rx_repo.allergy_terms_for_patient(encounter.patient_id),
        interacting_medication_ids=rx_repo.interacting_active_medication_ids(
            encounter.patient_id, medication_id
        ),
    )
    drug = DrugFacts(
        medication_id=medication.id,
        name=medication.name,
        drug_class=medication.drug_class,
        is_controlled=medication.is_controlled,
    )
    result = evaluate_prescription(
        drug, context, refills=refills, override_interaction=override_interaction
    )

    if not result.allowed:
        record_audit(
            session,
            action="prescription.blocked",
            actor_id=doctor_id,
            resource_type="medication",
            resource_id=medication_id,
            patient_id=encounter.patient_id,
            commit=True,
        )
        raise UnsafePrescription(result.message or "Prescription blocked",
                                 details={"reason": result.block_reason})

    prescription = rx_repo.add(
        Prescription(
            encounter_id=encounter_id,
            patient_id=encounter.patient_id,
            prescriber_id=doctor_id,
            medication_id=medication_id,
            dose=dose,
            refills=refills,
        )
    )
    record_audit(
        session,
        action="prescription.create",
        actor_id=doctor_id,
        resource_type="prescription",
        resource_id=prescription.id,
        patient_id=encounter.patient_id,
    )
    # Alert the patient that a new prescription was written (in-app feed, M9).
    notification_service.notify(
        session,
        user_id=encounter.patient_id,
        event_type="prescription.created",
        message=f"A new prescription was added ({medication.name}).",
        link="/clinical/prescriptions",
    )
    return prescription


def list_for_patient(session: Session, patient_id: int) -> list[Prescription]:
    """Return a patient's prescriptions (story D5)."""
    return PrescriptionRepository(session).list_for_patient(patient_id)
