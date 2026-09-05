"""Tests for the 1:1 role profile models (app.models.profile).

Verifies each profile links to its User via a shared primary key, that the
relationship loads the owning user, and that the 1:1 constraint (one profile row
per user) is enforced by the shared PK.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.models.base import Base
from app.models.profile import DoctorProfile, NurseProfile, PatientProfile
from app.models.user import User


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s
    engine.dispose()


def _make_user(session: Session, email: str, role: Role) -> User:
    user = User(email=email, password_hash="h", role=role)
    session.add(user)
    session.flush()
    return user


def test_patient_profile_links_to_user(session: Session) -> None:
    user = _make_user(session, "pat@example.com", Role.PATIENT)
    profile = PatientProfile(
        user_id=user.id, date_of_birth=date(1990, 5, 1), sex="F", phone="555-0100"
    )
    session.add(profile)
    session.commit()

    assert profile.user_id == user.id
    assert profile.user is user  # relationship loads the owning account


def test_doctor_profile_persists_professional_fields(session: Session) -> None:
    user = _make_user(session, "doc@example.com", Role.DOCTOR)
    session.add(DoctorProfile(user_id=user.id, specialty="Cardiology", license_no="LIC-1"))
    session.commit()

    stored = session.get(DoctorProfile, user.id)
    assert stored is not None
    assert stored.specialty == "Cardiology"
    assert stored.license_no == "LIC-1"


def test_nurse_profile_persists_ward(session: Session) -> None:
    user = _make_user(session, "nurse@example.com", Role.NURSE)
    session.add(NurseProfile(user_id=user.id, ward="ICU"))
    session.commit()

    assert session.get(NurseProfile, user.id).ward == "ICU"


def test_profile_is_one_to_one_per_user(session: Session) -> None:
    """The shared primary key forbids a second profile row for the same user."""
    user = _make_user(session, "pat2@example.com", Role.PATIENT)
    session.add(PatientProfile(user_id=user.id))
    session.commit()

    session.add(PatientProfile(user_id=user.id))
    with pytest.raises(IntegrityError):
        session.commit()


def test_doctor_license_is_unique(session: Session) -> None:
    a = _make_user(session, "doc1@example.com", Role.DOCTOR)
    b = _make_user(session, "doc2@example.com", Role.DOCTOR)
    session.add(DoctorProfile(user_id=a.id, license_no="DUP"))
    session.commit()

    session.add(DoctorProfile(user_id=b.id, license_no="DUP"))
    with pytest.raises(IntegrityError):
        session.commit()
