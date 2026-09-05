"""Tests for the auth service (app.services.auth_service).

Covers registration (happy path, profile creation, audit row, duplicate email)
and login (success tokens + audit, and the uniform-failure security property for
unknown email / wrong password / deactivated account).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import decode_token
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.profile import DoctorProfile, PatientProfile
from app.models.user import User
from app.schemas.auth import RegisterRequest
from app.schemas.user import UserCreate
from app.services import auth_service


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s
    engine.dispose()


def _register(session: Session, email: str = "pat@example.com") -> User:
    return auth_service.register_patient(
        session, RegisterRequest(email=email, password="longenough1")
    )


def test_register_creates_patient_with_profile_and_hashed_password(session: Session) -> None:
    user = _register(session)

    assert user.id is not None
    assert user.role is Role.PATIENT
    assert user.password_hash != "longenough1"  # stored hashed, not plaintext
    # A patient profile is created alongside the account.
    assert session.get(PatientProfile, user.id) is not None


def test_register_writes_audit_row(session: Session) -> None:
    user = _register(session)
    audits = session.scalars(select(AuditLog).where(AuditLog.action == "user.register")).all()
    assert len(audits) == 1
    assert audits[0].actor_id == user.id


def test_register_rejects_duplicate_email(session: Session) -> None:
    _register(session)
    with pytest.raises(auth_service.EmailAlreadyRegistered):
        _register(session)


def test_login_success_returns_tokens_and_audits(session: Session) -> None:
    user = _register(session)
    tokens = auth_service.login(session, "pat@example.com", "longenough1")

    claims = decode_token(tokens.access_token, expected_type="access")
    assert claims["sub"] == str(user.id)
    assert claims["role"] == "patient"
    # Refresh token is valid and of the right type.
    assert decode_token(tokens.refresh_token, expected_type="refresh")["sub"] == str(user.id)

    assert session.scalars(select(AuditLog).where(AuditLog.action == "auth.login")).all()


def test_login_wrong_password_is_rejected_and_audited(session: Session) -> None:
    _register(session)
    with pytest.raises(auth_service.InvalidCredentials):
        auth_service.login(session, "pat@example.com", "wrong-password")

    failures = session.scalars(
        select(AuditLog).where(AuditLog.action == "auth.login_failed")
    ).all()
    assert len(failures) == 1


def test_login_unknown_email_uses_same_error(session: Session) -> None:
    """Unknown email must raise the same error type as a wrong password."""
    with pytest.raises(auth_service.InvalidCredentials):
        auth_service.login(session, "nobody@example.com", "whatever12")


def test_login_deactivated_account_is_rejected(session: Session) -> None:
    user = _register(session)
    user.is_active = False
    session.flush()
    with pytest.raises(auth_service.InvalidCredentials):
        auth_service.login(session, "pat@example.com", "longenough1")


def test_refresh_issues_new_pair_and_audits(session: Session) -> None:
    _register(session)
    pair = auth_service.login(session, "pat@example.com", "longenough1")

    refreshed = auth_service.refresh_tokens(session, pair.refresh_token)
    # A valid new access token comes back.
    assert decode_token(refreshed.access_token, expected_type="access")["role"] == "patient"
    assert session.scalars(select(AuditLog).where(AuditLog.action == "auth.refresh")).all()


def test_refresh_rejects_access_token(session: Session) -> None:
    """Passing an access token to refresh must fail (story A4)."""
    _register(session)
    pair = auth_service.login(session, "pat@example.com", "longenough1")
    with pytest.raises(auth_service.InvalidCredentials):
        auth_service.refresh_tokens(session, pair.access_token)


def test_refresh_rejects_deactivated_user(session: Session) -> None:
    user = _register(session)
    pair = auth_service.login(session, "pat@example.com", "longenough1")
    user.is_active = False
    session.flush()
    with pytest.raises(auth_service.InvalidCredentials):
        auth_service.refresh_tokens(session, pair.refresh_token)


def test_provision_staff_creates_doctor_with_profile_and_audit(session: Session) -> None:
    doctor = auth_service.provision_staff(
        session,
        admin_id=1,
        payload=UserCreate(email="doc@example.com", password="longenough1", role=Role.DOCTOR),
    )
    assert doctor.role is Role.DOCTOR
    assert session.get(DoctorProfile, doctor.id) is not None
    audits = session.scalars(select(AuditLog).where(AuditLog.action == "user.provision")).all()
    assert len(audits) == 1
    assert audits[0].actor_id == 1


def test_provision_staff_rejects_patient_role(session: Session) -> None:
    with pytest.raises(auth_service.StaffRoleRequired):
        auth_service.provision_staff(
            session,
            admin_id=1,
            payload=UserCreate(email="x@example.com", password="longenough1", role=Role.PATIENT),
        )


def test_provision_staff_rejects_duplicate_email(session: Session) -> None:
    _register(session, "taken@example.com")
    with pytest.raises(auth_service.EmailAlreadyRegistered):
        auth_service.provision_staff(
            session,
            admin_id=1,
            payload=UserCreate(email="taken@example.com", password="longenough1", role=Role.NURSE),
        )


def test_set_user_active_toggles_and_audits(session: Session) -> None:
    from app.models.audit import AuditLog

    user = _register(session, "toggle@example.com")
    auth_service.set_user_active(session, admin_id=999, user_id=user.id, is_active=False)
    assert user.is_active is False
    actions = session.scalars(select(AuditLog.action).where(AuditLog.action == "user.deactivate")).all()
    assert list(actions)


def test_admin_cannot_deactivate_self(session: Session) -> None:
    from app.core.exceptions import PermissionDenied

    admin = _register(session, "admin2@example.com")
    with pytest.raises(PermissionDenied):
        auth_service.set_user_active(session, admin_id=admin.id, user_id=admin.id, is_active=False)
