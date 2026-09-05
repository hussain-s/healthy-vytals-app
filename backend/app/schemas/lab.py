"""Lab API schemas (v2 M8)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class LabOrderCreate(BaseModel):
    encounter_id: int
    test_code: str = Field(min_length=1, max_length=32)
    test_name: str = Field(min_length=1, max_length=128)
    notes: str | None = Field(default=None, max_length=500)


class LabOrderOut(ORMModel):
    id: int
    encounter_id: int
    patient_id: int
    ordered_by: int
    test_code: str
    test_name: str
    notes: str | None
    status: str


class LabResultCreate(BaseModel):
    analyte: str = Field(min_length=1, max_length=64)
    value: float
    unit: str | None = Field(default=None, max_length=32)
    reference_low: float | None = None
    reference_high: float | None = None


class LabResultOut(ORMModel):
    id: int
    lab_order_id: int
    recorded_by: int
    analyte: str
    value: float
    unit: str | None
    reference_low: float | None
    reference_high: float | None
    abnormal: bool
