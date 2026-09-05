"""Role-specific profile models — 1:1 extensions of a User.

Each clinical role carries attributes that only make sense for that role, so
rather than a wide, mostly-null ``users`` table we model them as separate
profile tables joined 1:1 to ``users`` (DESIGN §4.1):

    * :class:`PatientProfile` — demographics + insurance + emergency contact.
    * :class:`DoctorProfile`  — specialty + license number.
    * :class:`NurseProfile`   — assigned ward.

Why 1:1 profiles instead of columns on User:
    * keeps the ``users`` table focused on identity/auth;
    * lets each role's attributes evolve independently;
    * makes "which role is this?" a structural fact (a doctor has a
      DoctorProfile), not just an enum value, and gives clinical foreign keys a
      precise target (e.g. an AvailabilitySlot references a doctor).

``user_id`` is both the primary key and a foreign key to ``users.id`` — a shared
primary key is the canonical way to model a 1:1 relationship and guarantees at
most one profile row per user. ``ondelete="CASCADE"`` keeps the relational graph
consistent, though accounts are normally deactivated, not deleted (story E1).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.user import User


class PatientProfile(TimestampMixin, Base):
    """Demographic and contact details for a PATIENT user."""

    __tablename__ = "patient_profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    sex: Mapped[str | None] = mapped_column(String(16), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    insurance_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship()


class DoctorProfile(TimestampMixin, Base):
    """Professional details for a DOCTOR user."""

    __tablename__ = "doctor_profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    specialty: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # License numbers are unique across doctors when present.
    license_no: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )

    user: Mapped[User] = relationship()


class NurseProfile(TimestampMixin, Base):
    """Assignment details for a NURSE user."""

    __tablename__ = "nurse_profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    ward: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped[User] = relationship()
