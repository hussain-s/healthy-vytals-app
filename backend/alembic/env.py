"""Alembic migration environment for HealthyVytals.

Wires Alembic to the application so there is a single source of truth:

    * the database URL comes from the app's Settings (``HV_DATABASE_URL``), not a
      hard-coded value in alembic.ini — migrations always target the same DB the
      app uses;
    * ``target_metadata`` is the app's ``Base.metadata``, so ``alembic revision
      --autogenerate`` diffs the real ORM models.

All models must be imported before autogenerate runs, so their tables are
registered on ``Base.metadata`` (see ``_import_all_models``). Today there are no
models yet (Phase 1 adds the first); the import hook is in place so autogenerate
"just works" the moment models exist.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.models.base import Base

# Alembic Config object (values from alembic.ini).
config = context.config

# Configure Python logging from the ini file, if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _import_all_models() -> None:
    """Import every model module so its tables register on Base.metadata.

    Autogenerate can only see models that have been imported. As model modules
    are added under app/models/ in later phases, import them here.
    """
    from app.models import (  # noqa: F401  (register tables)
        audit,
        clinical,
        lab,
        messaging,
        notification,
        prescription,
        profile,
        scheduling,
        user,
    )


_import_all_models()
target_metadata = Base.metadata


def _database_url() -> str:
    """Return the migration target URL from application settings."""
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a live DB connection)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Compare column types and server defaults so autogenerate detects more
        # kinds of drift, not just added/removed tables and columns.
        compare_type=True,
        compare_server_default=True,
        # SQLite cannot ALTER most columns; batch mode renders such changes as
        # table-copy operations so migrations work on the default backend.
        render_as_batch=_database_url().startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (against a live DB connection)."""
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=_database_url().startswith("sqlite"),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
