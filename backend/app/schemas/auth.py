"""Authentication request/response schemas (the API boundary for auth).

These Pydantic models define exactly what the auth endpoints accept and return
(stories A1, A3, A4). They validate input at the boundary — an invalid email or
too-short password is rejected here, before any service or domain code runs — and
they never expose secrets (a login response carries tokens, never the password
hash).

Password policy is intentionally modest for an educational app (minimum length);
it lives on the request schema so the rule is declared once, at the boundary.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

# Minimum password length enforced at registration. Kept as a module constant so
# the rule is visible and testable rather than a magic number inline.
MIN_PASSWORD_LENGTH = 8


class RegisterRequest(BaseModel):
    """Payload for self-service patient registration (story A1).

    Only patients self-register; staff accounts are admin-provisioned (A2), so
    this request carries no role field — the service assigns the PATIENT role.
    """

    email: EmailStr = Field(description="Login email; must be unique.")
    password: str = Field(
        min_length=MIN_PASSWORD_LENGTH,
        max_length=128,
        description=f"Plaintext password (min {MIN_PASSWORD_LENGTH} chars); hashed server-side.",
    )
    full_name: str | None = Field(
        default=None, max_length=255, description="Optional display name."
    )


class LoginRequest(BaseModel):
    """Credentials for obtaining a token pair (story A3)."""

    email: EmailStr
    password: str = Field(min_length=1, description="Plaintext password to verify.")


class TokenPair(BaseModel):
    """The access + refresh tokens returned on login/refresh (stories A3, A4).

    ``token_type`` is the OAuth2 bearer convention so standard clients (and the
    Swagger UI) know how to send the access token: ``Authorization: Bearer ...``.
    """

    access_token: str
    refresh_token: str
    token_type: str = Field(default="bearer")


class RefreshRequest(BaseModel):
    """Payload to exchange a valid refresh token for a new token pair (story A4)."""

    refresh_token: str = Field(min_length=1)
