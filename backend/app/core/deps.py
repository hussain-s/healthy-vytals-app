"""FastAPI dependencies for authentication and authorization.

These bridge HTTP requests to identity + access decisions, reused by every
protected endpoint:

    * :func:`get_current_user` — resolve the caller from a JWT access token,
      accepted either as an ``Authorization: Bearer`` header (API/tests) or an
      HttpOnly session cookie (browser/web UI). Both paths decode to the same
      user, so the API and the server-rendered UI share one auth model (§7.3).
    * :func:`require_roles` — a dependency *factory* returning a guard that admits
      only the listed roles, raising 403 otherwise (story A5, coarse RBAC).

Fine-grained checks (ownership, treating-relationship §5.3) are NOT here — those
need domain data and live in the service layer.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError, PermissionDenied
from app.core.roles import Role
from app.core.security import TokenError, decode_token
from app.db.session import get_session
from app.models.user import User
from app.repositories.user_repository import UserRepository

# Name of the HttpOnly cookie carrying the access token for the browser UI.
SESSION_COOKIE_NAME = "hv_access"


def _extract_access_token(request: Request) -> str:
    """Return the access token from the Authorization header or session cookie.

    Prefers the ``Authorization: Bearer <token>`` header (used by the JSON API and
    tests); falls back to the HttpOnly cookie set at web login. Raises
    :class:`AuthenticationError` (401) if neither is present.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token

    raise AuthenticationError("Not authenticated")


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> User:
    """Resolve and return the authenticated :class:`User`, or raise 401.

    Decodes the access token (enforcing type + expiry + signature), loads the
    user, and rejects unknown or deactivated accounts. A deactivated account is
    treated as unauthenticated so a disabled user cannot keep acting on a
    still-valid token.
    """
    token = _extract_access_token(request)
    try:
        claims = decode_token(token, expected_type="access")
    except TokenError as exc:
        raise AuthenticationError("Could not validate credentials") from exc

    user_id = claims.get("sub")
    user = UserRepository(session).get(int(user_id)) if user_id is not None else None
    if user is None or not user.is_active:
        raise AuthenticationError("Could not validate credentials")
    return user


def require_roles(*allowed: Role) -> Callable[[User], User]:
    """Build a dependency that admits only users whose role is in ``allowed``.

    Usage::

        @router.get("/audit", dependencies=[Depends(require_roles(Role.ADMIN))])

    or bind the returned user::

        def handler(user: User = Depends(require_roles(Role.DOCTOR, Role.NURSE))):

    Raises :class:`PermissionDenied` (403) when the authenticated user's role is
    not permitted. This is the coarse gate; finer ownership checks live in
    services.
    """
    allowed_set = frozenset(allowed)

    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_set:
            raise PermissionDenied("You do not have permission to perform this action")
        return user

    return _guard
