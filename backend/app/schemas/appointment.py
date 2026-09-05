"""Appointment/scheduling API schemas (request/response shapes).

These define the boundary for publishing slots, booking, and viewing
appointments. Response models map from ORM instances via :class:`ORMModel`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.domain.appointment_state import AppointmentStatus
from app.schemas.common import ORMModel


class SlotCreate(BaseModel):
    """A doctor's request to publish one availability slot (story B1)."""

    start_at: datetime = Field(description="Slot start (timezone-aware).")
    end_at: datetime = Field(description="Slot end (timezone-aware); must be after start.")

    @model_validator(mode="after")
    def _check_interval(self) -> "SlotCreate":
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self


class SlotOut(ORMModel):
    """A published availability slot."""

    id: int
    doctor_id: int
    start_at: datetime
    end_at: datetime
    is_booked: bool


class BookingRequest(BaseModel):
    """A patient's request to book an open slot (story B2)."""

    slot_id: int = Field(description="The open slot to book.")
    reason: str | None = Field(default=None, max_length=500, description="Reason for visit.")


class AppointmentOut(ORMModel):
    """An appointment as returned to clients."""

    id: int
    patient_id: int
    doctor_id: int
    slot_id: int
    status: AppointmentStatus
    reason: str | None
    cancelled_late: bool
