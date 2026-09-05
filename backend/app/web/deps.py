"""Web-layer dependencies — cookie-session authentication for the browser UI.

The JSON API authenticates with a Bearer header; the server-rendered UI carries
the access token in an HttpOnly cookie (DESIGN §7.3). These helpers resolve the
current user from that cookie for HTML routes.

Two flavors are provided:
    * :func:`get_current_web_user` — returns the user or ``None`` (for pages that
      render differently when logged out, e.g. the landing/nav).
    * :func:`require_web_user` — returns the user or issues a redirect to the
      login page (for protected pages). Raising a redirect keeps the route bodies
      clean and the auth rule in one place.

Both read the same ``hv_access`` cookie and reuse the core token machinery, so
the browser and API share one identity model.
"""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.deps import SESSION_COOKIE_NAME
from app.core.security import TokenError, decode_token
from app.db.session import get_session
from app.models.user import User
from app.repositories.user_repository import UserRepository


class _RedirectToLogin(Exception):
    """Internal signal that a protected page needs the login redirect.

    Caught by a handler registered in the app factory, which turns it into a 303
    redirect to the login page. Using an exception keeps route bodies free of
    redirect plumbing.
    """


def get_current_web_user(
    request: Request,
    session: Session = Depends(get_session),
) -> User | None:
    """Resolve the browser's current user from the session cookie, or ``None``.

    Never raises for an anonymous visitor — returns ``None`` so templates can show
    logged-out state. A malformed/expired cookie or a deactivated account is
    treated as anonymous.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    try:
        claims = decode_token(token, expected_type="access")
    except TokenError:
        return None
    user_id = claims.get("sub")
    if user_id is None:
        return None
    user = UserRepository(session).get(int(user_id))
    return user if (user is not None and user.is_active) else None


def require_web_user(
    user: User | None = Depends(get_current_web_user),
) -> User:
    """Return the current user or raise the login redirect (protected pages)."""
    if user is None:
        raise _RedirectToLogin()
    return user


def _handle_login_redirect(_: Request, __: _RedirectToLogin) -> RedirectResponse:
    """Turn a _RedirectToLogin into a 303 See Other to the login page."""
    return RedirectResponse(url="/login", status_code=303)
