"""Appointments API endpoints (JSON).

Thin controllers over the appointment service, role-gated via dependencies. This
slice exposes doctor slot publishing + listing (story B1); booking and state
transitions are added in following slices.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.core.roles import Role
from app.db.session import get_session
from app.domain.appointment_state import Transition
from app.models.user import User
from app.repositories.appointment_repository import AppointmentRepository, SlotRepository
from app.schemas.appointment import AppointmentOut, BookingRequest, SlotCreate, SlotOut
from app.services import appointment_service

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.post(
    "/slots",
    response_model=SlotOut,
    status_code=status.HTTP_201_CREATED,
    summary="Publish an availability slot (doctor only)",
)
def publish_slot(
    payload: SlotCreate,
    doctor: User = Depends(require_roles(Role.DOCTOR)),
    session: Session = Depends(get_session),
) -> SlotOut:
    """Publish a bookable slot for the authenticated doctor (story B1)."""
    slot = appointment_service.publish_slot(
        session, doctor.id, payload.start_at, payload.end_at
    )
    return SlotOut.model_validate(slot)


@router.get(
    "/slots/mine",
    response_model=list[SlotOut],
    summary="List the current doctor's own slots",
)
def list_my_slots(
    doctor: User = Depends(require_roles(Role.DOCTOR)),
    session: Session = Depends(get_session),
) -> list[SlotOut]:
    """Return the authenticated doctor's published slots, earliest first."""
    slots = SlotRepository(session).list_for_doctor(doctor.id)
    return [SlotOut.model_validate(s) for s in slots]


@router.get(
    "/slots/open/{doctor_id}",
    response_model=list[SlotOut],
    summary="List a doctor's open slots (any authenticated user)",
)
def list_open_slots(
    doctor_id: int,
    _current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[SlotOut]:
    """Return a doctor's unbooked slots so a patient can choose one (story B2)."""
    slots = SlotRepository(session).list_open_for_doctor(doctor_id)
    return [SlotOut.model_validate(s) for s in slots]


@router.post(
    "",
    response_model=AppointmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Book an open slot (patient only)",
)
def book_appointment(
    payload: BookingRequest,
    patient: User = Depends(require_roles(Role.PATIENT)),
    session: Session = Depends(get_session),
) -> AppointmentOut:
    """Book an available slot for the authenticated patient (stories B2, B3).

    A taken slot or a buffer conflict raises ``SlotConflict`` → 409; an unknown
    slot is a 404.
    """
    appointment = appointment_service.book_appointment(
        session, patient.id, payload.slot_id, payload.reason
    )
    return AppointmentOut.model_validate(appointment)


@router.get(
    "/mine",
    response_model=list[AppointmentOut],
    summary="List the current patient's appointments",
)
def list_my_appointments(
    patient: User = Depends(require_roles(Role.PATIENT)),
    session: Session = Depends(get_session),
) -> list[AppointmentOut]:
    """Return the authenticated patient's appointments."""
    appointments = AppointmentRepository(session).list_for_patient(patient.id)
    return [AppointmentOut.model_validate(a) for a in appointments]


@router.get(
    "/doctor",
    response_model=list[AppointmentOut],
    summary="The current doctor's calendar",
)
def list_doctor_calendar(
    doctor: User = Depends(require_roles(Role.DOCTOR)),
    session: Session = Depends(get_session),
) -> list[AppointmentOut]:
    """Return the authenticated doctor's appointments (their calendar, story B5)."""
    appointments = AppointmentRepository(session).list_for_doctor(doctor.id)
    return [AppointmentOut.model_validate(a) for a in appointments]


@router.get(
    "/ward",
    response_model=list[AppointmentOut],
    summary="The day's schedule for nursing staff",
)
def list_ward_schedule(
    _nurse: User = Depends(require_roles(Role.NURSE)),
    session: Session = Depends(get_session),
) -> list[AppointmentOut]:
    """Return the ward schedule for a nurse (story B5).

    v1 scope: a nurse sees all appointments across the clinic (a single ward).
    Per-ward scoping is a documented future refinement — NurseProfile.ward exists
    to support it — but is out of v1 (DESIGN Non-Goals).
    """
    appointments = AppointmentRepository(session).list_all()
    return [AppointmentOut.model_validate(a) for a in appointments]


@router.post(
    "/{appointment_id}/transitions/{transition}",
    response_model=AppointmentOut,
    summary="Advance an appointment through its lifecycle",
)
def transition_appointment(
    appointment_id: int,
    transition: Transition,
    current: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> AppointmentOut:
    """Apply a state-machine transition (stories B4, B6; §5.1).

    Any authenticated user may call this; the pure state machine decides whether
    the caller's role may make the requested move (patient cancel/reschedule,
    nurse check-in/no-show, doctor confirm/begin/complete), returning 409 for an
    illegal move and 403 when a patient targets someone else's appointment.
    ``transition`` is validated against the Transition enum by FastAPI (422 if
    unknown).
    """
    appointment = appointment_service.change_status(
        session, current.id, current.role, appointment_id, transition
    )
    return AppointmentOut.model_validate(appointment)
