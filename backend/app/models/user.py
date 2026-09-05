"""User account model — the base identity every person in the system has.

A ``User`` is the authentication anchor: it holds the credentials (email +
bcrypt hash) and the role that drives authorization. Role-specific attributes
(a patient's date of birth, a doctor's license number, a nurse's ward) live on
separate 1:1 profile models (see ``profile.py``), not here — this keeps the
account concern cleanly separated from clinical/professional attributes and lets
each profile evolve independently.

Design notes:
    * ``email`` is the natural login identifier and is unique + indexed.
    * ``password_hash`` stores a bcrypt hash only — never a plaintext password.
      The column is named ``password_hash`` (not ``password``) so it is obvious
      at every call site that this is not reversible.
    * ``role`` is the :class:`~app.core.roles.Role` enum, persisted as its string
      value; it is what route guards and service-layer checks authorize against.
    * ``is_active`` supports soft-deactivation (admins deactivate accounts rather
      than deleting them — story E1) so history and audit references remain valid.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.roles import Role
from app.models.base import Base, IdMixin, TimestampMixin


class User(IdMixin, TimestampMixin, Base):
    """An authenticated account with a single role."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(
        # Persist the enum by value ("patient", ...) rather than by name, so the
        # stored data matches what appears in JWTs/JSON and stays readable in SQL.
        Enum(Role, native_enum=False, values_callable=lambda enum: [m.value for m in enum]),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<User id={self.id} email={self.email!r} role={self.role}>"
