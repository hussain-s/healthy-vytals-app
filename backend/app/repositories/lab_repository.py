"""Data-access for lab orders and results (v2 M8).

Confines lab queries to the DAL (DESIGN §7.6, rule 2). Services call these; they
never build queries themselves.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.lab import LabOrder, LabResult
from app.repositories.base import Repository


class LabOrderRepository(Repository[LabOrder]):
    def __init__(self, session: Session) -> None:
        super().__init__(LabOrder, session)

    def list_for_patient(self, patient_id: int) -> list[LabOrder]:
        stmt = (
            select(LabOrder)
            .where(LabOrder.patient_id == patient_id)
            .order_by(LabOrder.id.desc())
        )
        return list(self.session.scalars(stmt).all())

    def list_for_encounter(self, encounter_id: int) -> list[LabOrder]:
        stmt = (
            select(LabOrder)
            .where(LabOrder.encounter_id == encounter_id)
            .order_by(LabOrder.id)
        )
        return list(self.session.scalars(stmt).all())

    def pending(self) -> list[LabOrder]:
        """Orders still awaiting results (the lab/nurse work queue)."""
        stmt = (
            select(LabOrder)
            .where(LabOrder.status == "ordered")
            .order_by(LabOrder.id)
        )
        return list(self.session.scalars(stmt).all())


class LabResultRepository(Repository[LabResult]):
    def __init__(self, session: Session) -> None:
        super().__init__(LabResult, session)

    def list_for_order(self, lab_order_id: int) -> list[LabResult]:
        stmt = (
            select(LabResult)
            .where(LabResult.lab_order_id == lab_order_id)
            .order_by(LabResult.id)
        )
        return list(self.session.scalars(stmt).all())
