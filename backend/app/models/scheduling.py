"""Scheduling models — availability slots and appointments.

This module holds the persistence models for the scheduling domain:

    * :class:`AvailabilitySlot` — a bookable window a doctor publishes (story B1).
    * :class:`Appointment` — a patient's booking of a doctor's time, moving
      through the state machine in DESIGN §5.1 (added in a later slice).

Design notes:
    * A slot references its doctor by ``users.id``. We store the doctor as a User
      id (not a DoctorProfile id) so scheduling queries never need to join the
      profile table; the service layer guarantees the referenced user is a doctor.
    * ``is_booked`` is a denormalized flag for fast "show me open slots" queries.
      It is kept in lockstep with appointment creation/cancellation by the booking
      service inside a single transaction, so it can never drift from reality.
    * Times are timezone-aware. Slots are half-open intervals ``[start, end)`` — a
      slot ending at 10:00 and one starting at 10:00 do **not** overlap, which is
      the natural convention for back-to-back scheduling.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.appointment_state import AppointmentStatus
from app.models.base import Base, IdMixin, TimestampMixin


class AvailabilitySlot(IdMixin, TimestampMixin, Base):
    """A bookable time window published by a doctor (story B1)."""

    __tablename__ = "availability_slots"

    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_booked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    __table_args__ = (
        # The common query is "this doctor's slots, ordered by time" — e.g. a
        # patient browsing openings or the conflict check for a new slot.
        Index("ix_availability_slots_doctor_start", "doctor_id", "start_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return (
            f"<AvailabilitySlot id={self.id} doctor={self.doctor_id} "
            f"{self.start_at}..{self.end_at} booked={self.is_booked}>"
        )


class Appointment(IdMixin, TimestampMixin, Base):
    """A patient's booking of a doctor's slot, driven by the §5.1 state machine.

    The ``status`` column stores an :class:`AppointmentStatus` (defined in the
    domain layer, so the persisted enum and the state-machine rules share one
    source of truth). All status changes go through the state machine in the
    service layer; the model does not enforce transitions itself.

    Foreign keys reference ``users.id`` for patient and doctor (consistent with
    :class:`AvailabilitySlot`), and the originating slot. ``slot_id`` is unique so
    a slot can back at most one *active* appointment; the booking service frees the
    slot (``is_booked=False``) when an appointment is cancelled/rescheduled so it
    can be re-booked, and reuses the row's uniqueness to prevent double-booking.
    """

    __tablename__ = "appointments"

    patient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    slot_id: Mapped[int] = mapped_column(
        ForeignKey("availability_slots.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(
            AppointmentStatus,
            native_enum=False,
            values_callable=lambda enum: [m.value for m in enum],
        ),
        nullable=False,
        default=AppointmentStatus.REQUESTED,
        server_default=AppointmentStatus.REQUESTED.value,
        index=True,
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Set when a cancellation falls inside the cutoff window (§5.2). Kept for
    # policy/reporting; the state machine decides *whether* a cancel is legal, this
    # records *how* it was cancelled.
    cancelled_late: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    __table_args__ = (
        Index("ix_appointments_patient", "patient_id"),
        Index("ix_appointments_doctor", "doctor_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return (
            f"<Appointment id={self.id} patient={self.patient_id} "
            f"doctor={self.doctor_id} status={self.status}>"
        )
