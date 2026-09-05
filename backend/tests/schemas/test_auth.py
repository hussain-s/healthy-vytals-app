"""Tests for auth/user schemas (app.schemas.auth, app.schemas.user).

Confirms boundary validation (email format, password length) and — most
importantly — that UserOut cannot serialize a password hash even when built from
an ORM-like object carrying one.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.roles import Role
from app.schemas.auth import MIN_PASSWORD_LENGTH, LoginRequest, RegisterRequest, TokenPair
from app.schemas.user import UserOut


def test_register_request_accepts_valid_input() -> None:
    req = RegisterRequest(email="pat@example.com", password="longenough1")
    assert req.email == "pat@example.com"


def test_register_request_rejects_short_password() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="pat@example.com", password="short")
    assert MIN_PASSWORD_LENGTH == 8


def test_register_request_rejects_bad_email() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="not-an-email", password="longenough1")


def test_login_request_requires_nonempty_password() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(email="pat@example.com", password="")


def test_token_pair_defaults_to_bearer() -> None:
    pair = TokenPair(access_token="a", refresh_token="r")
    assert pair.token_type == "bearer"


def test_user_out_never_exposes_password_hash() -> None:
    """Building UserOut from an ORM-like object must drop password_hash."""

    class _FakeUser:
        id = 1
        email = "pat@example.com"
        role = Role.PATIENT
        is_active = True
        password_hash = "super-secret-hash"

    out = UserOut.model_validate(_FakeUser())
    dumped = out.model_dump()
    assert dumped["email"] == "pat@example.com"
    assert dumped["role"] == Role.PATIENT
    assert "password_hash" not in dumped
