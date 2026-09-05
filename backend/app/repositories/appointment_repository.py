"""Data-access for availability slots and appointments.

Confines all scheduling queries to the DAL (DESIGN §7.6, rule 2). The booking and
state-change services call these methods; they never build queries themselves.
The most important query here is :meth:`AppointmentRepository.active_windows_for_doctor`,
which feeds the pure conflict/buffer check in ``domain/scheduling_rules.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.domain.appointment_state import AppointmentStatus
from app.domain.scheduling_rules import TimeWindow
from app.models.scheduling import Appointment, AvailabilitySlot
from app.models.user import User
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

    def scheduled_for_doctor(self, doctor_id: int) -> list[dict]:
        """Return a doctor's appointments with slot time + patient email, by start.

        A display-oriented join for the doctor's worklist. Returns plain dicts
        (view rows), not ORM objects, so the web layer renders without lazy loads.
        """
        return self._scheduled(Appointment.doctor_id == doctor_id)

    def scheduled_all(self) -> list[dict]:
        """Return all appointments with slot time + patient email (nurse ward board)."""
        return self._scheduled(None)

    def scheduled_for_patient(self, patient_id: int) -> list[dict]:
        """Return a patient's appointments with slot time, by start (patient list).

        Display-oriented join like :meth:`scheduled_for_doctor`, so the patient's
        "My appointments" screen can show *when* each visit is and its doctor,
        without lazy-loading ORM relationships in the template.
        """
        return self._scheduled(Appointment.patient_id == patient_id)

    def _scheduled(self, where) -> list[dict]:
        # Alias User twice so a single row carries both the patient's and the
        # doctor's email — the doctor view wants the patient, the patient view
        # wants the doctor, and the nurse board wants both.
        patient_user = aliased(User)
        doctor_user = aliased(User)
        stmt = (
            select(
                Appointment.id,
                Appointment.status,
                Appointment.reason,
                Appointment.cancelled_late,
                Appointment.patient_id,
                Appointment.doctor_id,
                AvailabilitySlot.start_at,
                AvailabilitySlot.end_at,
                patient_user.email.label("patient_email"),
                doctor_user.email.label("doctor_email"),
            )
            .join(AvailabilitySlot, Appointment.slot_id == AvailabilitySlot.id)
            .join(patient_user, Appointment.patient_id == patient_user.id)
            .join(doctor_user, Appointment.doctor_id == doctor_user.id)
        )
        if where is not None:
            stmt = stmt.where(where)
        stmt = stmt.order_by(AvailabilitySlot.start_at)
        return [
            {
                "id": r.id,
                "status": r.status,
                "reason": r.reason,
                "cancelled_late": r.cancelled_late,
                "patient_id": r.patient_id,
                "doctor_id": r.doctor_id,
                "start_at": _as_utc(r.start_at),
                "end_at": _as_utc(r.end_at),
                "patient_email": r.patient_email,
                "doctor_email": r.doctor_email,
            }
            for r in self.session.execute(stmt)
        ]

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
