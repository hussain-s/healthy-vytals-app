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

from app.core.roles import Role
from app.models.user import User
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
) -> HTMLResponse:
    """Render the role-appropriate dashboard for the logged-in user.

    Unauthenticated visitors are redirected to /login by require_web_user. The
    per-role template is chosen from _DASHBOARD_TEMPLATE so each role lands on a
    view scoped to what it can do.
    """
    template = _DASHBOARD_TEMPLATE[user.role]
    return templates.TemplateResponse(request, template, {"user": user})
