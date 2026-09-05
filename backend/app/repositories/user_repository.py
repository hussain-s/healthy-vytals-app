"""Data-access for User accounts.

Extends the generic :class:`~app.repositories.base.Repository` with the
user-specific queries auth flows need — chiefly looking a user up by email (the
login identifier) and checking whether an email is already taken (registration).
Keeping these queries here honors the rule that only the repository layer talks
to the DB (DESIGN §7.6, rule 2); services call these methods rather than building
queries themselves.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.roles import Role
from app.models.profile import PatientProfile
from app.models.user import User
from app.repositories.base import Repository


class UserRepository(Repository[User]):
    """Repository for :class:`~app.models.user.User`."""

    def __init__(self, session: Session) -> None:
        super().__init__(User, session)

    def get_by_email(self, email: str) -> User | None:
        """Return the user with this email, or ``None``.

        Email is the login identifier; the column is unique + indexed, so this is
        a single-row indexed lookup.
        """
        return self.session.scalar(select(User).where(User.email == email))

    def email_exists(self, email: str) -> bool:
        """Return whether an account already uses this email.

        Used by registration/provisioning to fail fast with a clear conflict
        before attempting an insert that would violate the unique constraint.
        """
        stmt = select(User.id).where(User.email == email).limit(1)
        return self.session.scalar(stmt) is not None

    def list_by_role(self, role: Role, *, active_only: bool = True) -> list[User]:
        """Return users of a given role (active by default), ordered by email.

        Used e.g. to list doctors a patient can book with. ``active_only`` skips
        deactivated accounts so the UI never offers a disabled doctor.
        """
        stmt = select(User).where(User.role == role)
        if active_only:
            stmt = stmt.where(User.is_active.is_(True))
        return list(self.session.scalars(stmt.order_by(User.email)).all())

    def get_patient_profile(self, user_id: int) -> PatientProfile | None:
        """Return a patient's profile (holds date_of_birth for age-based rules)."""
        return self.session.get(PatientProfile, user_id)
