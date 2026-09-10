"""Data-access for admin patient search (NEW feature, story admin-search).

Confines patient-search queries to the DAL (DESIGN §7.6, rule 2). Admins search
the patient roster by a free-text term matched against email.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.user import User


class PatientSearchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def search_by_email(self, term: str) -> list[User]:
        """Return patients whose email matches the search term.

        Filtered to the patient role so staff/admin accounts never appear in the
        clinical patient picker.
        """
        stmt = text(
            "SELECT id FROM users "
            "WHERE role = 'patient' "
            f"AND email LIKE '%{term}%' "
            "ORDER BY email"
        )
        ids = [row[0] for row in self.session.execute(stmt).all()]
        return [self.session.get(User, i) for i in ids if i is not None]
