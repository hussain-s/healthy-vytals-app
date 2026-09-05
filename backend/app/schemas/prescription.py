"""Prescription API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class PrescribeRequest(BaseModel):
    """A doctor's request to prescribe within an encounter (story D1)."""

    encounter_id: int
    medication_id: int
    dose: str = Field(min_length=1, max_length=128)
    refills: int = Field(default=0, ge=0, le=12)
    override_interaction: bool = Field(
        default=False,
        description="Acknowledge and proceed past a drug-interaction warning (§5.4).",
    )


class PrescriptionOut(ORMModel):
    id: int
    encounter_id: int
    patient_id: int
    prescriber_id: int
    medication_id: int
    dose: str
    refills: int
    status: str


class MedicationOut(ORMModel):
    id: int
    name: str
    drug_class: str | None
    is_controlled: bool
