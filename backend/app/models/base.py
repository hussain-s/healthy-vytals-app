"""Declarative base and shared column mixins for all ORM models.

Every table in HealthyVytals inherits from :class:`Base` and, in practice, from
:class:`IdMixin` + :class:`TimestampMixin`, so all entities share:

    * a surrogate integer primary key ``id``;
    * ``created_at`` / ``updated_at`` audit timestamps maintained by the DB.

Centralizing these here keeps table definitions consistent and DRY, and gives
Alembic a single ``Base.metadata`` to autogenerate migrations against.

Note on immutability (DESIGN §5.6): several clinical tables are *append-only* at
the domain level — corrections are recorded as Addenda, never in-place edits.
``updated_at`` still exists on every row for operational forensics, but the
service layer forbids mutating clinical records; immutability is a business rule
enforced above the ORM, not a missing column here.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base. All models and ``Base.metadata`` derive from this."""


class IdMixin:
    """Adds a surrogate integer primary key ``id``.

    A surrogate key (rather than natural keys like email) keeps foreign keys
    small and stable even if a natural attribute later changes.
    """

    id: Mapped[int] = mapped_column(primary_key=True)


class TimestampMixin:
    """Adds ``created_at`` / ``updated_at`` timestamps maintained by the database.

    Both use ``server_default``/``onupdate`` with SQL ``now()`` so timestamps are
    set by the database, not the app — consistent regardless of which layer or
    process writes the row, and correct even under raw SQL. Columns are
    timezone-aware (``DateTime(timezone=True)``) to avoid naive-datetime bugs.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
