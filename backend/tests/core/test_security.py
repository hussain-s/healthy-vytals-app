"""Tests for password hashing and JWT handling (app.core.security).

These pin the security-critical behaviors: hashes are salted and verifiable,
tokens round-trip their subject/claims, expiry is enforced, and — the key
story-A4 requirement — an access token cannot be used where a refresh token is
expected, or vice versa.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.core.config import Settings
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


@pytest.fixture
def settings() -> Settings:
    """Isolated settings with a real (test) secret, ignoring any ambient .env."""
    return Settings(_env_file=None, jwt_secret_key="test-secret-not-the-default")  # type: ignore[call-arg]


# --- Password hashing ---


def test_hash_is_salted_and_not_plaintext() -> None:
    hashed = hash_password("s3cret-pw")
    assert hashed != "s3cret-pw"
    # bcrypt uses a random salt, so two hashes of the same password differ.
    assert hash_password("s3cret-pw") != hashed


def test_verify_password_accepts_correct_and_rejects_wrong() -> None:
    hashed = hash_password("s3cret-pw")
    assert verify_password("s3cret-pw", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_verify_password_handles_malformed_hash_gracefully() -> None:
    """A non-bcrypt stored value must not raise — it is simply not a match."""
    assert verify_password("anything", "not-a-real-hash") is False


# --- JWT round-trip and type enforcement ---


def test_access_token_round_trips_subject_and_extra_claims(settings: Settings) -> None:
    token = create_access_token("user-42", settings=settings, extra_claims={"role": "doctor"})
    claims = decode_token(token, expected_type="access", settings=settings)

    assert claims["sub"] == "user-42"
    assert claims["type"] == "access"
    assert claims["role"] == "doctor"


def test_refresh_token_round_trips(settings: Settings) -> None:
    token = create_refresh_token("user-42", settings=settings)
    claims = decode_token(token, expected_type="refresh", settings=settings)
    assert claims["sub"] == "user-42"
    assert claims["type"] == "refresh"


def test_access_token_rejected_as_refresh(settings: Settings) -> None:
    """Story A4: an access token must not be accepted where refresh is required."""
    token = create_access_token("user-42", settings=settings)
    with pytest.raises(TokenError, match="type mismatch"):
        decode_token(token, expected_type="refresh", settings=settings)


def test_refresh_token_rejected_as_access(settings: Settings) -> None:
    token = create_refresh_token("user-42", settings=settings)
    with pytest.raises(TokenError, match="type mismatch"):
        decode_token(token, expected_type="access", settings=settings)


def test_tampered_or_wrong_key_token_is_rejected(settings: Settings) -> None:
    token = create_access_token("user-42", settings=settings)
    other = Settings(_env_file=None, jwt_secret_key="a-different-secret")  # type: ignore[call-arg]
    with pytest.raises(TokenError):
        decode_token(token, expected_type="access", settings=other)


def test_extra_claims_cannot_override_reserved(settings: Settings) -> None:
    with pytest.raises(ValueError, match="reserved claims"):
        create_access_token("user-42", settings=settings, extra_claims={"sub": "hacker"})


def test_expiry_is_enforced_with_backdated_token(settings: Settings) -> None:
    """A token whose exp is in the past must be rejected by decode_token."""
    now = datetime.now(timezone.utc)
    expired = jwt.encode(
        {
            "sub": "user-42",
            "type": "access",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(TokenError):
        decode_token(expired, expected_type="access", settings=settings)
