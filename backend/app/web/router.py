"""Web (HTML) routes — the server-rendered presentation layer.

These routes render Jinja2 templates and return HTML. They are deliberately thin:
they gather data (in later phases, by calling the same services the JSON API
uses) and render a template. No business logic, no direct DB access (DESIGN §7.6,
rule 7).

This bootstrap slice provides the landing page and one HTMX partial endpoint to
prove the server-render + HTMX loop works end to end.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.db.session import get_session
from app.models.user import User
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.prescription_repository import PrescriptionRepository
from app.repositories.user_repository import UserRepository
from app.web.deps import require_web_user
from app.web.templates import templates

router = APIRouter(include_in_schema=False)

# The dashboard template to render for each role.
_DASHBOARD_TEMPLATE = {
    Role.PATIENT: "dashboard/patient.html",
    Role.NURSE: "dashboard/nurse.html",
    Role.DOCTOR: "dashboard/doctor.html",
    Role.ADMIN: "dashboard/admin.html",
}

# Appointment statuses considered "open work" on a clinician worklist/board.
_OPEN_STATUSES = {"requested", "confirmed", "checked_in", "in_progress"}


def _dashboard_context(session: Session, user: User) -> dict:
    """Build the per-role dashboard view model from the existing repositories.

    Kept in the web layer as read-only composition (no business decisions); each
    role sees a summary scoped to what it can act on.
    """
    if user.role is Role.DOCTOR:
        appts = AppointmentRepository(session).scheduled_for_doctor(user.id)
        open_appts = [a for a in appts if a["status"].value in _OPEN_STATUSES]
        patients = sorted({a["patient_email"] for a in appts})
        return {
            "appointments": appts,
            "open_appointments": open_appts,
            "open_count": len(open_appts),
            "patient_count": len(patients),
            "patients": patients,
        }
    if user.role is Role.NURSE:
        appts = AppointmentRepository(session).scheduled_all()
        awaiting = [a for a in appts if a["status"].value == "confirmed"]
        return {"appointments": appts, "awaiting_checkin": awaiting,
                "awaiting_count": len(awaiting), "total_count": len(appts)}
    if user.role is Role.ADMIN:
        users = UserRepository(session)
        counts = {r.value: len(users.list_by_role(r, active_only=False)) for r in Role}
        return {"role_counts": counts, "total_users": sum(counts.values())}
    # Patient
    patient_appts = AppointmentRepository(session).list_for_patient(user.id)
    upcoming = [a for a in patient_appts if a.status.value in _OPEN_STATUSES]
    rx = PrescriptionRepository(session).list_for_patient(user.id)
    active_rx = [r for r in rx if r.status == "active"]
    return {
        "upcoming_count": len(upcoming),
        "active_rx_count": len(active_rx),
        "appointment_count": len(patient_appts),
    }


@router.get("/", response_class=HTMLResponse, name="web-landing")
def landing(request: Request) -> HTMLResponse:
    """Render the public landing page.

    ``request`` is required by Jinja2Templates so templates can use ``url_for``
    to build links/asset URLs from route names (keeping URLs in one place).
    """
    return templates.TemplateResponse(request, "landing.html")


@router.get("/_status", response_class=HTMLResponse, name="web-status")
def status_partial(request: Request) -> HTMLResponse:
    """Render the status fragment swapped into the landing page by HTMX.

    Returns only a partial (no full HTML document) — the unit HTMX swaps into the
    target element. Kept trivial for the bootstrap; later this pattern powers
    dashboards, booking lists, etc.
    """
    return templates.TemplateResponse(
        request,
        "partials/status.html",
        {"status": "ok", "database": "ok"},
    )


@router.get("/dashboard", response_class=HTMLResponse, name="web-dashboard")
def dashboard(
    request: Request,
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Render the role-appropriate dashboard for the logged-in user.

    Unauthenticated visitors are redirected to /login by require_web_user. The
    per-role template is chosen from _DASHBOARD_TEMPLATE and populated with a
    read-only summary scoped to what that role can act on.
    """
    template = _DASHBOARD_TEMPLATE[user.role]
    context = {"user": user, **_dashboard_context(session, user)}
    return templates.TemplateResponse(request, template, context)
