"""Data-access for prescriptions and the facts the safety checks consult.

Confines prescription queries to the DAL (DESIGN §7.6, rule 2). The safety-fact
queries here (allergy terms, interacting active medications) feed the pure
evaluator in ``domain/prescription_safety.py``.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.prescription import (
    Allergy,
    DrugInteraction,
    Medication,
    Prescription,
)
from app.repositories.base import Repository


class MedicationRepository(Repository[Medication]):
    def __init__(self, session: Session) -> None:
        super().__init__(Medication, session)

    def get_by_name(self, name: str) -> Medication | None:
        return self.session.scalar(select(Medication).where(Medication.name == name))


class PrescriptionRepository(Repository[Prescription]):
    def __init__(self, session: Session) -> None:
        super().__init__(Prescription, session)

    def allergy_terms_for_patient(self, patient_id: int) -> frozenset[str]:
        """Return the patient's allergy substances/classes, lower-cased.

        These are matched against the candidate drug's name and class by the pure
        allergy check (§5.4).
        """
        rows = self.session.scalars(
            select(Allergy.substance).where(Allergy.patient_id == patient_id)
        ).all()
        return frozenset(term.lower() for term in rows)

    def active_medication_ids_for_patient(self, patient_id: int) -> set[int]:
        """Return the medication ids of the patient's currently-active prescriptions."""
        rows = self.session.scalars(
            select(Prescription.medication_id).where(
                Prescription.patient_id == patient_id,
                Prescription.status == "active",
            )
        ).all()
        return set(rows)

    def interacting_active_medication_ids(
        self, patient_id: int, medication_id: int
    ) -> frozenset[int]:
        """Return the patient's active meds that interact with ``medication_id``.

        Looks up the candidate's interaction partners (in either column of the
        unordered pair) and intersects with the patient's active medications.
        Non-empty means an interaction is present (§5.4).
        """
        partners = set(
            self.session.scalars(
                select(DrugInteraction.medication_b_id).where(
                    DrugInteraction.medication_a_id == medication_id
                )
            ).all()
        ) | set(
            self.session.scalars(
                select(DrugInteraction.medication_a_id).where(
                    DrugInteraction.medication_b_id == medication_id
                )
            ).all()
        )
        active = self.active_medication_ids_for_patient(patient_id)
        return frozenset(partners & active)

    def list_for_patient(self, patient_id: int) -> list[Prescription]:
        return list(
            self.session.scalars(
                select(Prescription)
                .where(Prescription.patient_id == patient_id)
                .order_by(Prescription.id)
            ).all()
        )
