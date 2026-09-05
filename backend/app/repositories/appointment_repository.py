"""Data-access for availability slots and appointments.

Confines all scheduling queries to the DAL (DESIGN §7.6, rule 2). The booking and
state-change services call these methods; they never build queries themselves.
The most important query here is :meth:`AppointmentRepository.active_windows_for_doctor`,
which feeds the pure conflict/buffer check in ``domain/scheduling_rules.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.appointment_state import AppointmentStatus
from app.domain.scheduling_rules import TimeWindow
from app.models.scheduling import Appointment, AvailabilitySlot
from app.repositories.base import Repository

# Appointment states that still occupy a slot for conflict purposes. Cancelled,
# no-show, and (arguably) completed no longer block new bookings; the live states
# below are the ones a new booking must not overlap.
_BLOCKING_STATES: frozenset[AppointmentStatus] = frozenset(
    {
        AppointmentStatus.REQUESTED,
        AppointmentStatus.CONFIRMED,
        AppointmentStatus.CHECKED_IN,
        AppointmentStatus.IN_PROGRESS,
    }
)


def _as_utc(value: datetime) -> datetime:
    """Coerce a datetime read from the DB to timezone-aware UTC.

    SQLite does not persist tzinfo, so datetimes come back naive; we treat stored
    times as UTC (they are always written as UTC) and attach tzinfo. This keeps
    the pure domain layer working with consistent aware datetimes and avoids
    naive/aware comparison errors.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


class SlotRepository(Repository[AvailabilitySlot]):
    """Repository for :class:`AvailabilitySlot`."""

    def __init__(self, session: Session) -> None:
        super().__init__(AvailabilitySlot, session)

    def list_for_doctor(self, doctor_id: int) -> list[AvailabilitySlot]:
        """Return a doctor's slots, earliest first."""
        stmt = (
            select(AvailabilitySlot)
            .where(AvailabilitySlot.doctor_id == doctor_id)
            .order_by(AvailabilitySlot.start_at)
        )
        return list(self.session.scalars(stmt).all())

    def list_open_for_doctor(self, doctor_id: int) -> list[AvailabilitySlot]:
        """Return a doctor's *unbooked* slots, earliest first (for patients)."""
        stmt = (
            select(AvailabilitySlot)
            .where(
                AvailabilitySlot.doctor_id == doctor_id,
                AvailabilitySlot.is_booked.is_(False),
            )
            .order_by(AvailabilitySlot.start_at)
        )
        return list(self.session.scalars(stmt).all())


class AppointmentRepository(Repository[Appointment]):
    """Repository for :class:`Appointment`."""

    def __init__(self, session: Session) -> None:
        super().__init__(Appointment, session)

    def list_for_patient(self, patient_id: int) -> list[Appointment]:
        stmt = (
            select(Appointment)
            .where(Appointment.patient_id == patient_id)
            .order_by(Appointment.id)
        )
        return list(self.session.scalars(stmt).all())

    def list_for_doctor(self, doctor_id: int) -> list[Appointment]:
        stmt = (
            select(Appointment)
            .where(Appointment.doctor_id == doctor_id)
            .order_by(Appointment.id)
        )
        return list(self.session.scalars(stmt).all())

    def list_all(self) -> list[Appointment]:
        """Return every appointment (the v1 single-ward nurse schedule, story B5)."""
        return list(self.session.scalars(select(Appointment).order_by(Appointment.id)).all())

    def active_windows_for_doctor(
        self, doctor_id: int, exclude_appointment_id: int | None = None
    ) -> list[TimeWindow]:
        """Return the time windows of a doctor's currently-blocking appointments.

        Joins appointments in a blocking state to their slots and returns the slot
        intervals as :class:`TimeWindow` value objects, ready for the pure
        conflict/buffer check. ``exclude_appointment_id`` omits a given appointment
        (used when re-checking during a reschedule so it doesn't conflict with
        itself).
        """
        stmt = (
            select(AvailabilitySlot.start_at, AvailabilitySlot.end_at)
            .join(Appointment, Appointment.slot_id == AvailabilitySlot.id)
            .where(
                Appointment.doctor_id == doctor_id,
                Appointment.status.in_(_BLOCKING_STATES),
            )
        )
        if exclude_appointment_id is not None:
            stmt = stmt.where(Appointment.id != exclude_appointment_id)
        return [
            TimeWindow(start=_as_utc(start), end=_as_utc(end))
            for start, end in self.session.execute(stmt)
        ]
