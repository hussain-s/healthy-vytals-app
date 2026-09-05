"""Tests for demo data seeding (app.db.seed).

Runs the real seed() against a temp SQLite database (via the app's engine/session,
with caches cleared) and asserts it creates one user per role, is idempotent, and
that a seeded account can actually authenticate.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.roles import Role
from app.db import seed as seed_module
from app.db import session as db_session
from app.models.base import Base
from app.models.user import User
from app.services import auth_service


@pytest.fixture
def temp_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("HV_DATABASE_URL", f"sqlite:///{tmp_path / 'seed.db'}")
    for cached in (get_settings, db_session.get_engine, db_session.get_sessionmaker):
        cached.cache_clear()
    Base.metadata.create_all(db_session.get_engine())
    try:
        yield
    finally:
        db_session.get_engine().dispose()
        for cached in (get_settings, db_session.get_engine, db_session.get_sessionmaker):
            cached.cache_clear()


def test_seed_creates_one_user_per_role(temp_db: None) -> None:
    seed_module.seed()
    with db_session.get_sessionmaker()() as s:
        roles = set(s.scalars(select(User.role)).all())
    assert roles == {Role.PATIENT, Role.NURSE, Role.DOCTOR, Role.ADMIN}


def test_seed_is_idempotent(temp_db: None) -> None:
    seed_module.seed()
    seed_module.seed()  # second run must not duplicate
    with db_session.get_sessionmaker()() as s:
        count = s.scalar(select(func.count()).select_from(User))
    assert count == len(seed_module._DEMO_USERS)


def test_seeded_user_can_authenticate(temp_db: None) -> None:
    seed_module.seed()
    with db_session.unit_of_work() as s:
        tokens = auth_service.login(s, "doctor@healthyvytals.example.com", seed_module.DEMO_PASSWORD)
    assert tokens.access_token


def test_seed_creates_medications_and_interactions(temp_db: None) -> None:
    from app.models.prescription import DrugInteraction, Medication

    seed_module.seed()
    with db_session.get_sessionmaker()() as s:
        med_count = s.scalar(select(func.count()).select_from(Medication))
        interaction_count = s.scalar(select(func.count()).select_from(DrugInteraction))
    assert med_count == len(seed_module._DEMO_MEDICATIONS)
    assert interaction_count == len(seed_module._DEMO_INTERACTIONS)


def test_medication_seed_is_idempotent(temp_db: None) -> None:
    from app.models.prescription import Medication

    seed_module.seed()
    seed_module.seed()
    with db_session.get_sessionmaker()() as s:
        med_count = s.scalar(select(func.count()).select_from(Medication))
    assert med_count == len(seed_module._DEMO_MEDICATIONS)


def test_seed_creates_one_clinical_journey_idempotently(temp_db: None) -> None:
    from app.models.clinical import Diagnosis, Encounter
    from app.models.prescription import Prescription
    from app.models.scheduling import Appointment

    seed_module.seed()
    seed_module.seed()  # second run must not duplicate the journey
    with db_session.get_sessionmaker()() as s:
        assert s.scalar(select(func.count()).select_from(Appointment)) == 1
        assert s.scalar(select(func.count()).select_from(Encounter)) == 1
        assert s.scalar(select(func.count()).select_from(Diagnosis)) == 1
        assert s.scalar(select(func.count()).select_from(Prescription)) == 1
