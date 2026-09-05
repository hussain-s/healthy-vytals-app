"""Application configuration — the single source of truth for runtime settings.

All configuration is environment-driven (twelve-factor style) with safe local
defaults, so the app runs on a fresh clone with **no** ``.env`` file. Every
setting can be overridden by an environment variable or a ``.env`` file, using
the ``HV_`` prefix (e.g. ``HV_DATABASE_URL``). See ``.env.example`` for the
documented list.

Design notes:
    * SQLite is the default database (decision §12.2) — zero setup, no server,
      no Docker. Postgres is opt-in purely by changing ``HV_DATABASE_URL``; no
      code changes are needed because SQLAlchemy selects the driver from the URL.
    * Domain tunables (appointment buffer, cancellation cutoff) live here so the
      business rules in §5.2 read their thresholds from one place rather than
      hard-coding magic numbers in the domain layer.
    * ``Settings`` is a cached singleton (:func:`get_settings`) so the ``.env``
      file and environment are parsed once per process.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The well-known placeholder shipped in .env.example. Acceptable for local dev
# only; we refuse to boot with it when HV_ENV=production (see _guard_production).
_INSECURE_JWT_SECRET = "dev-only-insecure-change-me"


class Settings(BaseSettings):
    """Strongly-typed application settings loaded from the environment / ``.env``.

    Field names are lower-case; the ``HV_`` prefix is applied when reading from
    the environment, so ``jwt_secret_key`` is populated from ``HV_JWT_SECRET_KEY``.
    """

    model_config = SettingsConfigDict(
        env_prefix="HV_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Core application ---
    env: str = Field(
        default="development",
        description='Environment label; "production" enables stricter safety checks.',
    )

    # --- Database (decision §12.2) ---
    database_url: str = Field(
        default="sqlite:///./healthyvytals.db",
        description="SQLAlchemy URL. Defaults to a local SQLite file; set a "
        "postgresql+psycopg:// URL to use Postgres with no code changes.",
    )

    # --- Security / auth (JWT access + refresh, bcrypt hashing) ---
    jwt_secret_key: str = Field(
        default=_INSECURE_JWT_SECRET,
        description="Signing key for JWTs. Must be overridden outside development.",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm.")
    access_token_expire_minutes: int = Field(
        default=30, ge=1, description="Lifetime of an access token, in minutes."
    )
    refresh_token_expire_days: int = Field(
        default=7, ge=1, description="Lifetime of a refresh token, in days."
    )

    # --- Domain tunables (business rules — DESIGN §5.2) ---
    appointment_buffer_minutes: int = Field(
        default=10,
        ge=0,
        description="Minimum gap enforced between a doctor's appointments (§5.2).",
    )
    cancellation_cutoff_hours: int = Field(
        default=24,
        ge=0,
        description="Cancellations inside this window are allowed but flagged late (§5.2).",
    )

    @property
    def is_production(self) -> bool:
        """True when running in a production-labelled environment."""
        return self.env.strip().lower() == "production"

    @property
    def is_sqlite(self) -> bool:
        """True when the configured database is SQLite (affects engine args in db/)."""
        return self.database_url.startswith("sqlite")

    @model_validator(mode="after")
    def _guard_production(self) -> Settings:
        """Fail fast if production is misconfigured with the insecure dev secret.

        Booting a production deployment while still signing tokens with the
        publicly-known placeholder key would let anyone forge sessions. We refuse
        to start rather than silently run insecurely.
        """
        if self.is_production and self.jwt_secret_key == _INSECURE_JWT_SECRET:
            raise ValueError(
                "HV_JWT_SECRET_KEY is still the insecure development default while "
                "HV_ENV=production. Set a real secret, e.g. "
                '`python -c "import secrets; print(secrets.token_urlsafe(48))"`.'
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` singleton.

    Cached so the environment and ``.env`` file are read exactly once. Tests that
    need to exercise different configuration can call ``get_settings.cache_clear()``
    after setting environment variables.
    """
    return Settings()
