"""User request/response schemas (the API boundary for accounts).

Response models here map from ORM ``User`` instances via :class:`ORMModel`
(``from_attributes``), exposing only safe fields. Critically, ``UserOut`` has no
``password_hash`` field, so the credential hash can never be serialized to a
client even if a router accidentally passes the ORM object — the deliberate
schema boundary from DESIGN §7.6 rule 4.
"""

from __future__ import annotations

from pydantic import EmailStr, Field

from app.core.roles import Role
from app.schemas.common import ORMModel


class UserOut(ORMModel):
    """Public representation of a user account (never includes the password hash)."""

    id: int
    email: EmailStr
    role: Role
    is_active: bool


class UserCreate(ORMModel):
    """Admin payload to provision a staff account (story A2).

    Unlike self-service registration, this carries an explicit ``role`` because
    an admin chooses whether the new account is a doctor, nurse, or another admin.
    The service rejects PATIENT here — patients self-register (A1).
    """

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Role
    full_name: str | None = Field(default=None, max_length=255)
