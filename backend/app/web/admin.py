"""Web (HTML/HTMX) admin console: user management + audit-log viewer.

Admin-only screens (story E1/E2/E3). Thin over auth_service / audit_service; the
admin-only rule is enforced by :func:`_require_admin`. No business logic here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, PermissionDenied
from app.core.roles import Role
from app.db.session import get_session
from app.models.user import User
from app.schemas.user import UserCreate
from app.services import audit_service, auth_service
from app.web.deps import require_web_user
from app.web.templates import templates

router = APIRouter(prefix="/admin", include_in_schema=False)


def _require_admin(user: User = Depends(require_web_user)) -> User:
    if user.role is not Role.ADMIN:
        raise PermissionDenied("Admins only")
    return user


@router.get("/users", response_class=HTMLResponse, name="web-admin-users")
def users_console(
    request: Request,
    admin: User = Depends(_require_admin),
    session: Session = Depends(get_session),
    error: str | None = None,
) -> HTMLResponse:
    """List all accounts + a form to provision staff (story E1)."""
    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "user": admin,
            "users": auth_service.list_all_users(session),
            "roles": [r.value for r in (Role.DOCTOR, Role.NURSE, Role.ADMIN)],
            "error": error,
        },
    )


@router.post("/users", name="web-admin-provision")
def provision(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    admin: User = Depends(_require_admin),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """Provision a staff account, then re-render the console (with any error)."""
    error = None
    try:
        payload = UserCreate(email=email, password=password, role=Role(role))
        auth_service.provision_staff(session, admin.id, payload)
    except (AppError, ValueError) as exc:
        error = getattr(exc, "message", str(exc))
    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "user": admin,
            "users": auth_service.list_all_users(session),
            "roles": [r.value for r in (Role.DOCTOR, Role.NURSE, Role.ADMIN)],
            "error": error,
        },
        status_code=200 if error is None else 400,
    )


@router.post("/users/{user_id}/toggle", name="web-admin-toggle-user")
def toggle_user(
    user_id: int,
    is_active: str = Form(...),
    admin: User = Depends(_require_admin),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    """Activate/deactivate an account (story E1), then back to the console."""
    auth_service.set_user_active(session, admin.id, user_id, is_active == "true")
    return RedirectResponse(url="/admin/users", status_code=303)


@router.get("/audit", response_class=HTMLResponse, name="web-admin-audit")
def audit_viewer(
    request: Request,
    admin: User = Depends(_require_admin),
    session: Session = Depends(get_session),
    action: str = "",
) -> HTMLResponse:
    """View recent audit entries, optionally filtered by action (story E2)."""
    rows = audit_service.list_audit(session, action=action or None, limit=200)
    return templates.TemplateResponse(
        request, "admin/audit.html", {"user": admin, "rows": rows, "action": action},
    )
