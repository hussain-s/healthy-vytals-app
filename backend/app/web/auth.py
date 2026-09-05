"""Web (HTML) authentication routes — cookie-session login/logout/register.

These render forms and, on success, set or clear the HttpOnly ``hv_access``
cookie that the browser uses for subsequent requests (DESIGN §7.3). They call the
same :mod:`app.services.auth_service` the JSON API uses — no duplicated logic.

On a failed login/register we re-render the form with an error message and an
appropriate status code, rather than returning JSON, because these endpoints
serve the browser.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.deps import SESSION_COOKIE_NAME
from app.core.exceptions import AppError
from app.db.session import get_session
from app.schemas.auth import RegisterRequest
from app.services import auth_service
from app.web.templates import templates

router = APIRouter(include_in_schema=False)

# Access-token cookie lifetime is bounded by the token's own expiry; we also set
# a max_age so the browser drops it. HttpOnly blocks JS access (XSS defense);
# SameSite=Lax is a reasonable CSRF baseline for a local-first app.
_COOKIE_MAX_AGE = 30 * 60  # seconds; matches the default access-token lifetime


def _set_session_cookie(response: RedirectResponse, access_token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=access_token,
        httponly=True,
        samesite="lax",
        max_age=_COOKIE_MAX_AGE,
    )


@router.get("/login", response_class=HTMLResponse, name="web-login")
def login_form(request: Request) -> HTMLResponse:
    """Render the login form."""
    return templates.TemplateResponse(request, "auth/login.html")


@router.post("/login", name="web-login-submit")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    """Verify credentials; on success set the cookie and redirect to the dashboard."""
    try:
        tokens = auth_service.login(session, email, password)
    except AppError:
        # Re-render with a generic error (do not reveal which field was wrong).
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Incorrect email or password.", "email": email},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(response, tokens.access_token)
    return response


@router.get("/register", response_class=HTMLResponse, name="web-register")
def register_form(request: Request) -> HTMLResponse:
    """Render the patient self-registration form."""
    return templates.TemplateResponse(request, "auth/register.html")


@router.post("/register", name="web-register-submit")
def register_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
):
    """Register a patient; on success log them in and redirect to the dashboard."""
    try:
        payload = RegisterRequest(email=email, password=password)
    except ValueError:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"error": "Enter a valid email and a password of at least 8 characters.", "email": email},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    try:
        auth_service.register_patient(session, payload)
        tokens = auth_service.login(session, email, password)
    except AppError:
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"error": "That email is already registered.", "email": email},
            status_code=status.HTTP_409_CONFLICT,
        )
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(response, tokens.access_token)
    return response


@router.post("/logout", name="web-logout")
def logout() -> RedirectResponse:
    """Clear the session cookie and return to the landing page."""
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
