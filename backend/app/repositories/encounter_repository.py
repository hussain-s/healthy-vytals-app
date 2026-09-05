"""Data-access for clinical records (encounters, vitals, diagnoses, addenda).

Confines clinical queries to the DAL (DESIGN §7.6, rule 2). Two queries carry
domain weight: :meth:`has_treating_relationship` (feeds the §5.3 scoping
predicate) and the per-patient history assembly used by the read endpoints.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.clinical import Addendum, Diagnosis, Encounter, Vitals
from app.models.scheduling import Appointment
from app.repositories.base import Repository


class EncounterRepository(Repository[Encounter]):
    """Repository for :class:`Encounter` plus its clinical children."""

    def __init__(self, session: Session) -> None:
        super().__init__(Encounter, session)

    def get_by_appointment(self, appointment_id: int) -> Encounter | None:
        return self.session.scalar(
            select(Encounter).where(Encounter.appointment_id == appointment_id)
        )

    def list_for_patient(self, patient_id: int) -> list[Encounter]:
        stmt = (
            select(Encounter)
            .where(Encounter.patient_id == patient_id)
            .order_by(Encounter.opened_at)
        )
        return list(self.session.scalars(stmt).all())

    def has_treating_relationship(self, doctor_id: int, patient_id: int) -> bool:
        """Return whether the doctor treats (or has treated) the patient (§5.3).

        True if they share any appointment OR any encounter. Appointments count
        even before an encounter is opened, so a doctor a patient has booked with
        can see their history to prepare — matching the clinical intent.
        """
        appt = self.session.scalar(
            select(Appointment.id)
            .where(Appointment.doctor_id == doctor_id, Appointment.patient_id == patient_id)
            .limit(1)
        )
        if appt is not None:
            return True
        enc = self.session.scalar(
            select(Encounter.id)
            .where(Encounter.doctor_id == doctor_id, Encounter.patient_id == patient_id)
            .limit(1)
        )
        return enc is not None

    # --- clinical children ---

    def add_vitals(self, vitals: Vitals) -> Vitals:
        self.session.add(vitals)
        self.session.flush()
        return vitals

    def add_diagnosis(self, diagnosis: Diagnosis) -> Diagnosis:
        self.session.add(diagnosis)
        self.session.flush()
        return diagnosis

    def add_addendum(self, addendum: Addendum) -> Addendum:
        self.session.add(addendum)
        self.session.flush()
        return addendum

    def vitals_for_encounter(self, encounter_id: int) -> list[Vitals]:
        return list(
            self.session.scalars(
                select(Vitals).where(Vitals.encounter_id == encounter_id).order_by(Vitals.id)
            ).all()
        )

    def diagnoses_for_encounter(self, encounter_id: int) -> list[Diagnosis]:
        return list(
            self.session.scalars(
                select(Diagnosis)
                .where(Diagnosis.encounter_id == encounter_id)
                .order_by(Diagnosis.id)
            ).all()
        )
