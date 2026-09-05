"""Authentication service — registration, login, and token refresh use cases.

This is the application layer for accounts: it orchestrates repositories, the
security primitives (hashing/JWT), and the audit trail into complete use cases,
inside a caller-provided unit of work. Routers (JSON API and web) call these
functions; they contain no HTTP concerns themselves.

Security posture enforced here:
    * Only patients self-register (story A1); staff are admin-provisioned (A2).
    * Login is uniform on failure — a wrong email and a wrong password return the
      *same* error, so the endpoint does not reveal which emails are registered.
    * Every auth outcome is audited (§5.7), including failed logins.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError, Conflict
from app.core.roles import Role
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.profile import DoctorProfile, NurseProfile, PatientProfile
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import RegisterRequest, TokenPair
from app.schemas.user import UserCreate
from app.services.audit_service import record_audit

# Maps each role to the profile model created alongside the account. ADMIN has
# no profile (it carries no clinical/professional attributes).
_PROFILE_BY_ROLE = {
    Role.PATIENT: PatientProfile,
    Role.DOCTOR: DoctorProfile,
    Role.NURSE: NurseProfile,
}


class EmailAlreadyRegistered(Conflict):
    """Registration attempted with an email that already has an account."""

    code = "email_already_registered"


class InvalidCredentials(AuthenticationError):
    """Login failed. Deliberately identical for unknown email and wrong password."""

    code = "invalid_credentials"


class StaffRoleRequired(Conflict):
    """Admin provisioning was attempted with the PATIENT role.

    Patients self-register (story A1); the admin provisioning path is only for
    staff (doctor/nurse/admin), so PATIENT here is a client error, not a 500.
    """

    code = "staff_role_required"


def _create_account(session: Session, email: str, password: str, role: Role) -> User:
    """Create a User with its role-appropriate profile (shared by register/provision).

    Centralizes the "user + matching profile" invariant so every account-creation
    path produces a consistent object graph. Raises :class:`EmailAlreadyRegistered`
    if the email is taken.
    """
    users = UserRepository(session)
    if users.email_exists(email):
        raise EmailAlreadyRegistered(f"Email is already registered: {email}")

    user = users.add(
        User(email=email, password_hash=hash_password(password), role=role)
    )
    profile_cls = _PROFILE_BY_ROLE.get(role)
    if profile_cls is not None:
        session.add(profile_cls(user_id=user.id))
    session.flush()
    return user


def _issue_tokens(user: User) -> TokenPair:
    """Mint an access+refresh pair for ``user``.

    The user's id is the token subject; the role rides on the access token so
    guards can authorize without a DB round-trip. Refresh tokens carry no role.
    """
    return TokenPair(
        access_token=create_access_token(str(user.id), extra_claims={"role": user.role.value}),
        refresh_token=create_refresh_token(str(user.id)),
    )


def register_patient(session: Session, payload: RegisterRequest) -> User:
    """Register a new self-service patient account (story A1).

    Creates the User (PATIENT role, hashed password) and its 1:1 PatientProfile,
    then audits the registration — all within the caller's unit of work, so the
    account, profile, and audit row commit atomically. Raises
    :class:`EmailAlreadyRegistered` if the email is taken.
    """
    user = _create_account(session, payload.email, payload.password, Role.PATIENT)
    record_audit(
        session,
        action="user.register",
        actor_id=user.id,
        resource_type="user",
        resource_id=user.id,
    )
    return user


def provision_staff(session: Session, admin_id: int, payload: UserCreate) -> User:
    """Create a staff account on an admin's behalf (story A2).

    Staff (doctor/nurse/admin) are not self-service; an admin provisions them with
    an explicit role. Rejects the PATIENT role (those self-register). Audits the
    action with the admin as actor and the new account as the resource.
    """
    if payload.role is Role.PATIENT:
        raise StaffRoleRequired("Patients self-register; choose a staff role")

    user = _create_account(session, payload.email, payload.password, payload.role)
    record_audit(
        session,
        action="user.provision",
        actor_id=admin_id,
        resource_type="user",
        resource_id=user.id,
    )
    return user


def login(session: Session, email: str, password: str) -> TokenPair:
    """Verify credentials and return a token pair (story A3).

    On any failure — unknown email, wrong password, or a deactivated account —
    raises :class:`InvalidCredentials` with an identical message and audits an
    ``auth.login_failed`` event. On success, audits ``auth.login`` and issues
    tokens.
    """
    users = UserRepository(session)
    user = users.get_by_email(email)

    if user is None or not verify_password(password, user.password_hash) or not user.is_active:
        # Audit the failure. actor_id is the user id when the account exists
        # (wrong password / deactivated) and None for an unknown email. commit=True
        # so the audit row survives the request rollback triggered by the raise
        # below (the audit row is the only pending write here).
        record_audit(
            session,
            action="auth.login_failed",
            actor_id=user.id if user is not None else None,
            resource_type="user",
            commit=True,
        )
        raise InvalidCredentials("Incorrect email or password")

    record_audit(
        session,
        action="auth.login",
        actor_id=user.id,
        resource_type="user",
        resource_id=user.id,
    )
    return _issue_tokens(user)


def refresh_tokens(session: Session, refresh_token: str) -> TokenPair:
    """Exchange a valid refresh token for a fresh token pair (story A4).

    Enforces that the token is specifically a *refresh* token (an access token is
    rejected here — see :func:`~app.core.security.decode_token`), that the subject
    still resolves to an active account, and audits the outcome. A deactivated or
    unknown subject is rejected so a leaked refresh token for a disabled account
    cannot mint new access tokens.
    """
    try:
        claims = decode_token(refresh_token, expected_type="refresh")
    except TokenError as exc:
        # commit=True: persist the failure audit before the request rolls back.
        record_audit(session, action="auth.refresh_failed", resource_type="user", commit=True)
        raise InvalidCredentials("Invalid or expired refresh token") from exc

    user_id = claims.get("sub")
    user = UserRepository(session).get(int(user_id)) if user_id is not None else None
    if user is None or not user.is_active:
        record_audit(
            session,
            action="auth.refresh_failed",
            actor_id=user.id if user is not None else None,
            resource_type="user",
            commit=True,
        )
        raise InvalidCredentials("Invalid or expired refresh token")

    record_audit(
        session,
        action="auth.refresh",
        actor_id=user.id,
        resource_type="user",
        resource_id=user.id,
    )
    return _issue_tokens(user)
