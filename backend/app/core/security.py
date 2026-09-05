"""Security primitives: password hashing and JWT creation/decoding.

This module is the low-level cryptographic boundary. It knows nothing about
FastAPI, the database, or HTTP; it turns passwords into hashes and claims into
signed tokens (and back). Higher layers (services, deps) build auth flows on top.

Two token *types* are issued (see DESIGN §3, stories A3–A4):
    * **access**  — short-lived, sent on every request to prove identity.
    * **refresh** — long-lived, used only to mint new access tokens.

Both are JWTs carrying a ``type`` claim. :func:`decode_token` enforces the
expected type, so an access token can never be replayed where a refresh token is
required (or vice versa) — story A4's explicit security requirement.

All time handling is timezone-aware UTC. ``exp`` is a standard registered claim,
so python-jose validates expiry for us and raises on expired tokens.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import Settings, get_settings

# bcrypt via passlib. bcrypt embeds the salt and cost factor in the hash string,
# so no separate salt column is needed and the parameters travel with the hash.
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

TokenType = Literal["access", "refresh"]


class TokenError(Exception):
    """Raised when a token is invalid, expired, or of an unexpected type.

    Deliberately coarse: callers should not learn *why* a token failed (expired
    vs. tampered vs. wrong type), only that authentication did not succeed.
    ``core/errors.py`` maps this to a 401 without leaking detail.
    """


# --- Password hashing -------------------------------------------------------


def hash_password(plain_password: str) -> str:
    """Return a bcrypt hash of ``plain_password`` (salt + cost embedded)."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Return whether ``plain_password`` matches the stored ``password_hash``.

    Uses passlib's constant-time verification to avoid leaking match information
    through timing. Never raises on a malformed stored hash — returns ``False``.
    """
    try:
        return _pwd_context.verify(plain_password, password_hash)
    except ValueError:
        # Stored hash was not a recognizable bcrypt string; treat as no match
        # rather than surfacing an error to the auth path.
        return False


# --- JWT create / decode ----------------------------------------------------


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    settings: Settings,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Build and sign a JWT with standard registered claims plus ``type``.

    Claims: ``sub`` (subject, typically the user id), ``type`` (access/refresh),
    ``iat`` (issued-at), and ``exp`` (expiry). Additional non-reserved claims may
    be supplied via ``extra_claims`` (e.g. the user's role on the access token).
    """
    now = datetime.now(timezone.utc)
    claims: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    if extra_claims:
        # Reserved claims are set above and must not be overridden by callers.
        reserved = claims.keys() & extra_claims.keys()
        if reserved:
            raise ValueError(f"extra_claims may not override reserved claims: {reserved}")
        claims.update(extra_claims)
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(
    subject: str,
    settings: Settings | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a short-lived access token for ``subject``.

    ``extra_claims`` is where the caller attaches per-request context such as the
    user's role, so guards can authorize without an extra DB lookup.
    """
    settings = settings or get_settings()
    return _create_token(
        subject=subject,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        settings=settings,
        extra_claims=extra_claims,
    )


def create_refresh_token(subject: str, settings: Settings | None = None) -> str:
    """Create a long-lived refresh token for ``subject``.

    Refresh tokens carry no role/authorization claims by design — they are only
    an instrument to obtain a fresh access token, not to authorize actions.
    """
    settings = settings or get_settings()
    return _create_token(
        subject=subject,
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
        settings=settings,
    )


def decode_token(
    token: str,
    expected_type: TokenType,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Decode and validate ``token``, enforcing signature, expiry, and type.

    Returns the claims dict on success. Raises :class:`TokenError` if the token
    is malformed, has a bad signature, is expired, or does not carry the
    ``expected_type`` — the last check is what stops an access token being used
    as a refresh token and vice versa (story A4).
    """
    settings = settings or get_settings()
    try:
        claims = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except JWTError as exc:  # bad signature, expired, malformed, ...
        raise TokenError("Could not validate credentials") from exc

    if claims.get("type") != expected_type:
        raise TokenError("Token type mismatch")
    if "sub" not in claims:
        raise TokenError("Token missing subject")
    return claims
