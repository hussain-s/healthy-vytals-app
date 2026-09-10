"""Patient search service (NEW feature) — admin roster lookup.

Thin orchestration over the search repository. Admin-only; the coarse role gate
lives in the router.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.patient_search_repository import PatientSearchRepository


def search_patients(session: Session, term: str) -> list[User]:
    """Return patients matching the free-text term."""
    return PatientSearchRepository(session).search_by_email(term)
