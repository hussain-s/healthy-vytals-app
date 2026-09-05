"""Tests for env-driven application settings (app.core.config).

Covers the defaults that make a fresh clone run with no .env, environment-driven
overrides via the HV_ prefix, and the production safety guard that refuses to
boot with the insecure development secret.
"""

from __future__ import annotations

import pytest

from app.core.config import _INSECURE_JWT_SECRET, Settings


def test_defaults_are_local_first() -> None:
    """With no environment overrides, defaults target zero-setup local dev."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.env == "development"
    assert settings.is_production is False
    # SQLite by default (decision §12.2) so there's no server to install.
    assert settings.database_url.startswith("sqlite")
    assert settings.is_sqlite is True
    # Domain tunables match the documented business-rule defaults (§5.2).
    assert settings.appointment_buffer_minutes == 10
    assert settings.cancellation_cutoff_hours == 24


def test_environment_overrides_take_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings read HV_-prefixed environment variables and coerce types."""
    monkeypatch.setenv("HV_DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    monkeypatch.setenv("HV_APPOINTMENT_BUFFER_MINUTES", "15")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.is_sqlite is False
    assert settings.appointment_buffer_minutes == 15  # coerced from str to int


def test_production_rejects_insecure_default_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Booting production with the placeholder JWT secret must fail fast."""
    monkeypatch.setenv("HV_ENV", "production")
    monkeypatch.setenv("HV_JWT_SECRET_KEY", _INSECURE_JWT_SECRET)

    with pytest.raises(ValueError, match="HV_JWT_SECRET_KEY"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_production_accepts_a_real_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """A production environment with a real secret is allowed to start."""
    monkeypatch.setenv("HV_ENV", "production")
    monkeypatch.setenv("HV_JWT_SECRET_KEY", "a-real-and-sufficiently-long-secret-value")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.is_production is True
