"""Web (HTML/HTMX) appointment screens for patients.

Thin presentation over the same appointment service the JSON API uses (DESIGN
§7.6, rule 7): a booking page listing doctors and their open slots, an HTMX
endpoint that books a slot and swaps back a confirmation partial, and the
patient's own appointment list.

These pages are patient-scoped: :func:`_require_patient` enforces that the
logged-in web user is a patient (staff have their own dashboards), reusing the
cookie-session resolver.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.roles import Role
from app.db.session import get_session
from app.domain.appointment_state import Transition
from app.models.user import User
from app.repositories.appointment_repository import AppointmentRepository, SlotRepository
from app.repositories.user_repository import UserRepository
from app.services import appointment_service
from app.web.deps import require_web_user
from app.web.templates import templates

router = APIRouter(prefix="/appointments", include_in_schema=False)


def _require_patient(user: User = Depends(require_web_user)) -> User:
    """Ensure the web caller is a patient; redirect others to their dashboard.

    Raising the same redirect signal require_web_user uses would send them to
    login; instead we simply 403 via the typed error, which the HTML error path
    surfaces. For v1 the booking screens are patient-only by design.
    """
    if user.role is not Role.PATIENT:
        from app.core.exceptions import PermissionDenied

        raise PermissionDenied("Only patients can book appointments here")
    return user


def _doctors_with_slots(session: Session) -> list[dict]:
    """Build the view model: each active doctor plus their open slots."""
    users = UserRepository(session)
    slots = SlotRepository(session)
    result: list[dict] = []
    for doctor in users.list_by_role(Role.DOCTOR):
        open_slots = slots.list_open_for_doctor(doctor.id)
        if open_slots:
            result.append({"doctor": doctor, "slots": open_slots})
    return result


@router.get("/book", response_class=HTMLResponse, name="web-book")
def book_page(
    request: Request,
    patient: User = Depends(_require_patient),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Render the booking page: doctors with open slots to choose from (B2)."""
    return templates.TemplateResponse(
        request,
        "appointments/book.html",
        {"user": patient, "doctors": _doctors_with_slots(session)},
    )


@router.post("/book", response_class=HTMLResponse, name="web-book-submit")
def book_submit(
    request: Request,
    slot_id: int = Form(...),
    reason: str | None = Form(None),
    patient: User = Depends(_require_patient),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Book the chosen slot and swap in a confirmation (or error) partial.

    Returns an HTMX fragment: on success a confirmation, on a domain error (slot
    taken, etc.) an inline error message — so the page updates in place without a
    full reload.
    """
    try:
        appointment = appointment_service.book_appointment(
            session, patient.id, slot_id, reason
        )
    except AppError as exc:
        return templates.TemplateResponse(
            request,
            "appointments/partials/book_result.html",
            {"error": exc.message},
            status_code=exc.http_status,
        )
    return templates.TemplateResponse(
        request,
        "appointments/partials/book_result.html",
        {"appointment": appointment},
    )


@router.get("/mine", response_class=HTMLResponse, name="web-my-appointments")
def my_appointments(
    request: Request,
    patient: User = Depends(_require_patient),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """List the patient's own appointments with slot times and doctor (B-series)."""
    appointments = AppointmentRepository(session).scheduled_for_patient(patient.id)
    return templates.TemplateResponse(
        request,
        "appointments/mine.html",
        {"user": patient, "appointments": appointments, "cancellable": _CANCELLABLE},
    )


# Statuses from which a patient may still cancel (mirrors the §5.1 state machine).
_CANCELLABLE = {"requested", "confirmed", "checked_in"}


@router.post("/{appointment_id}/cancel", response_class=HTMLResponse,
             name="web-appointment-cancel")
def cancel_appointment(
    request: Request,
    appointment_id: int,
    patient: User = Depends(_require_patient),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Cancel one of the patient's appointments and re-render their list (B4).

    Delegates to ``appointment_service.change_status`` with the CANCEL transition,
    which enforces ownership + the state machine, frees the slot, flags a late
    cancellation, and audits. Re-renders the whole list partial so the row's new
    status (and freed slot) shows immediately via HTMX.
    """
    error: str | None = None
    try:
        appointment_service.change_status(
            session, patient.id, patient.role, appointment_id, Transition.CANCEL
        )
    except AppError as exc:
        error = exc.message
    appointments = AppointmentRepository(session).scheduled_for_patient(patient.id)
    return templates.TemplateResponse(
        request,
        "appointments/partials/appointment_list.html",
        {"appointments": appointments, "cancellable": _CANCELLABLE, "error": error},
    )
