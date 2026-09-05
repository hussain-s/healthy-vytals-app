"""Authentication API endpoints (JSON).

Thin controllers over :mod:`app.services.auth_service`: parse/validate via
Pydantic, call one service function inside a request-scoped unit of work
(``get_session``), and shape the response. No business logic lives here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_session
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from app.schemas.user import UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new patient account",
)
def register(
    payload: RegisterRequest,
    session: Session = Depends(get_session),
) -> UserOut:
    """Self-service patient registration (story A1).

    Returns the created account as :class:`UserOut` (never the password hash).
    A duplicate email raises ``EmailAlreadyRegistered`` → 409 via the typed-error
    handlers.
    """
    user = auth_service.register_patient(session, payload)
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenPair, summary="Log in and obtain tokens")
def login(
    payload: LoginRequest,
    session: Session = Depends(get_session),
) -> TokenPair:
    """Verify credentials and return an access + refresh token pair (story A3).

    Invalid credentials raise ``InvalidCredentials`` → 401, with an identical
    error whether the email is unknown or the password is wrong.
    """
    return auth_service.login(session, payload.email, payload.password)


@router.post("/refresh", response_model=TokenPair, summary="Refresh the token pair")
def refresh(
    payload: RefreshRequest,
    session: Session = Depends(get_session),
) -> TokenPair:
    """Exchange a valid refresh token for a fresh token pair (story A4).

    An access token presented here is rejected — only refresh tokens are accepted.
    """
    return auth_service.refresh_tokens(session, payload.refresh_token)


@router.get("/me", response_model=UserOut, summary="Return the current user")
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    """Return the authenticated caller (story A5 — proves auth resolution)."""
    return UserOut.model_validate(current_user)
