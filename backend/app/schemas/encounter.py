"""Clinical API schemas: encounters, vitals, diagnoses, addenda, history."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class EncounterOpen(BaseModel):
    """Request to open an encounter from an appointment."""

    appointment_id: int


class EncounterOut(ORMModel):
    id: int
    appointment_id: int
    patient_id: int
    doctor_id: int
    opened_at: datetime
    closed_at: datetime | None
    sensitive: bool
    consent_shared: bool


class VitalsCreate(BaseModel):
    """Nurse-recorded vitals; every field optional (record what was measured)."""

    heart_rate: int | None = Field(default=None, ge=0, le=400)
    resp_rate: int | None = Field(default=None, ge=0, le=120)
    systolic_bp: int | None = Field(default=None, ge=0, le=400)
    temp_c: float | None = Field(default=None, ge=20, le=45)
    spo2: int | None = Field(default=None, ge=0, le=100)


class VitalsOut(ORMModel):
    id: int
    encounter_id: int
    recorded_by: int
    heart_rate: int | None
    resp_rate: int | None
    systolic_bp: int | None
    temp_c: float | None
    spo2: int | None
    flags: str


class DiagnosisCreate(BaseModel):
    icd_code: str = Field(min_length=1, max_length=16)
    description: str = Field(min_length=1, max_length=1000)


class DiagnosisOut(ORMModel):
    id: int
    encounter_id: int
    author_id: int
    icd_code: str
    description: str


class AddendumCreate(BaseModel):
    target_type: str = Field(min_length=1, max_length=32)
    target_id: int
    note: str = Field(min_length=1, max_length=2000)


class AddendumOut(ORMModel):
    id: int
    target_type: str
    target_id: int
    author_id: int
    note: str
