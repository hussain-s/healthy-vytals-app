"""Appointment service — slot publishing, booking, and state changes.

Orchestrates the scheduling use cases inside a caller-provided unit of work,
wiring the pure domain rules (state machine §5.1, scheduling rules §5.2) to
persistence (repositories) and the audit trail. HTTP concerns stay in the routers.

This slice covers slot publishing (story B1); booking and state advancement land
in following slices.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import Conflict, NotFound, PermissionDenied, ValidationError
from app.core.roles import Role
from app.domain.appointment_state import (
    AppointmentStatus,
    Transition,
    assert_transition_allowed,
)
from app.domain.scheduling_rules import (
    TimeWindow,
    conflicts_with_buffer,
    is_late_cancellation,
)
from app.models.scheduling import Appointment, AvailabilitySlot
from app.repositories.appointment_repository import AppointmentRepository, SlotRepository
from app.services import notification_service
from app.services.audit_service import record_audit

# Transitions that release the slot back to bookable when applied.
_SLOT_FREEING = frozenset({Transition.CANCEL})


class SlotConflict(Conflict):
    """A booking was attempted against a slot that is taken or conflicts (§5.2)."""

    code = "slot_conflict"


def publish_slot(
    session: Session, doctor_id: int, start_at: datetime, end_at: datetime
) -> AvailabilitySlot:
    """Publish a new availability slot for a doctor (story B1).

    Validates the interval and rejects a slot that would conflict with the
    doctor's existing appointments (with the configured buffer, §5.2) — publishing
    over a booked commitment makes no sense. Two open slots may currently overlap
    each other; the conflict that matters is against *booked* time, and booking
    itself re-checks. Audits ``slot.publish``.
    """
    if end_at <= start_at:
        raise ValidationError("Slot end must be after its start")

    settings = get_settings()
    candidate = TimeWindow(start=start_at, end=end_at)
    existing = AppointmentRepository(session).active_windows_for_doctor(doctor_id)
    if conflicts_with_buffer(candidate, existing, settings.appointment_buffer_minutes):
        raise ValidationError(
            "Slot conflicts with an existing appointment (including buffer)",
            details={"buffer_minutes": settings.appointment_buffer_minutes},
        )

    slot = SlotRepository(session).add(
        AvailabilitySlot(doctor_id=doctor_id, start_at=start_at, end_at=end_at)
    )
    record_audit(
        session,
        action="slot.publish",
        actor_id=doctor_id,
        resource_type="availability_slot",
        resource_id=slot.id,
    )
    return slot


def book_appointment(
    session: Session, patient_id: int, slot_id: int, reason: str | None
) -> Appointment:
    """Book an open slot for a patient (stories B2, B3; rule §5.2).

    Steps, all inside the caller's unit of work so they commit atomically:
      1. Load the slot; 404 if it does not exist.
      2. Reject an already-booked slot (SlotConflict) — the fast, common guard.
      3. Re-run the buffer-aware conflict check against the doctor's active
         appointments, so a booking can't sneak inside another's buffer window.
      4. Mark the slot booked and create the appointment in ``requested``.
      5. Audit ``appointment.book``.

    The slot's ``is_booked`` flag plus the unique ``slot_id`` on appointments give
    two layers of double-booking protection; see :func:`book_appointment` callers
    and DESIGN §5.2 for the concurrency note.
    """
    slots = SlotRepository(session)
    slot = slots.get(slot_id)
    if slot is None:
        raise NotFound(f"No such slot: {slot_id}")
    if slot.is_booked:
        raise SlotConflict("That slot is no longer available")

    settings = get_settings()
    candidate = TimeWindow(start=slot.start_at, end=slot.end_at)
    existing = AppointmentRepository(session).active_windows_for_doctor(slot.doctor_id)
    if conflicts_with_buffer(candidate, existing, settings.appointment_buffer_minutes):
        raise SlotConflict("That time conflicts with another appointment")

    slot.is_booked = True
    session.flush()

    appointment = AppointmentRepository(session).add(
        Appointment(
            patient_id=patient_id,
            doctor_id=slot.doctor_id,
            slot_id=slot.id,
            status=AppointmentStatus.REQUESTED,
            reason=reason,
        )
    )
    record_audit(
        session,
        action="appointment.book",
        actor_id=patient_id,
        resource_type="appointment",
        resource_id=appointment.id,
        patient_id=patient_id,
    )
    # Alert the doctor that a new appointment was requested (in-app feed, M9).
    notification_service.notify(
        session,
        user_id=slot.doctor_id,
        event_type="appointment.booked",
        message="A patient booked an appointment with you.",
        link="/dashboard",
    )
    return appointment


def change_status(
    session: Session,
    actor_id: int,
    actor_role: Role,
    appointment_id: int,
    transition: Transition,
) -> Appointment:
    """Apply a state-machine transition to an appointment (stories B4, B6; §5.1).

    Loads the appointment (404 if missing), then delegates legality + role
    permission to the pure state machine (:func:`assert_transition_allowed`),
    which raises ``IllegalTransition`` (409) on an illegal move or a role that may
    not trigger it. Beyond the generic rules:

      * a **patient** may only act on their **own** appointment (ownership check
        that role alone can't express — 403 otherwise);
      * **cancelling** frees the slot (``is_booked=False``) so it can be re-booked,
        and sets ``cancelled_late`` when inside the cutoff window (§5.2), without
        blocking the cancellation.

    Audits ``appointment.<transition>``. All within the caller's unit of work.
    """
    repo = AppointmentRepository(session)
    appointment = repo.get(appointment_id)
    if appointment is None:
        raise NotFound(f"No such appointment: {appointment_id}")

    # Ownership: a patient may only drive their own appointment.
    if actor_role is Role.PATIENT and appointment.patient_id != actor_id:
        raise PermissionDenied("You may only change your own appointments")

    new_status = assert_transition_allowed(
        appointment.status, transition, actor_role
    )

    if transition in _SLOT_FREEING:
        slot = SlotRepository(session).get(appointment.slot_id)
        if slot is not None:
            slot.is_booked = False
        # Flag a late cancellation (does not block it — §5.2).
        cutoff = get_settings().cancellation_cutoff_hours
        slot_start = slot.start_at if slot is not None else None
        if slot_start is not None:
            if slot_start.tzinfo is None:
                slot_start = slot_start.replace(tzinfo=timezone.utc)
            appointment.cancelled_late = is_late_cancellation(
                datetime.now(timezone.utc), slot_start, cutoff
            )

    appointment.status = new_status
    session.flush()

    record_audit(
        session,
        action=f"appointment.{transition.value}",
        actor_id=actor_id,
        resource_type="appointment",
        resource_id=appointment.id,
        patient_id=appointment.patient_id,
    )
    # Notify the *other* party of a status change so both sides stay informed
    # (e.g. the doctor when a patient cancels, or the patient when staff do). M9.
    recipient_id = (
        appointment.doctor_id if actor_id == appointment.patient_id else appointment.patient_id
    )
    notification_service.notify(
        session,
        user_id=recipient_id,
        event_type=f"appointment.{transition.value}",
        message=f"An appointment was {transition.value.replace('_', ' ')}.",
        link="/dashboard",
    )
    return appointment
