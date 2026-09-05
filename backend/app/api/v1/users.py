"""User administration API endpoints (JSON), admin-only.

Thin controllers over the auth/user services, gated by ``require_roles(ADMIN)``
so only administrators can provision staff accounts (story A2). Business logic
(email uniqueness, profile creation, audit) lives in the service.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.roles import Role
from app.db.session import get_session
from app.models.user import User
from app.schemas.user import UserCreate, UserOut
from app.services import auth_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Provision a staff account (admin only)",
)
def provision_staff(
    payload: UserCreate,
    admin: User = Depends(require_roles(Role.ADMIN)),
    session: Session = Depends(get_session),
) -> UserOut:
    """Create a doctor/nurse/admin account on the admin's behalf (story A2).

    Requires an admin caller (403 otherwise). A PATIENT role is rejected with a
    409 (patients self-register); a duplicate email is a 409.
    """
    user = auth_service.provision_staff(session, admin.id, payload)
    return UserOut.model_validate(user)
