"""Tests for auth/authorization dependencies (app.core.deps).

Mounts throwaway protected routes on an app wired to a test database, then
exercises get_current_user (header + cookie, missing/invalid token, deactivated
user) and require_roles (allow/deny) end to end.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.deps import SESSION_COOKIE_NAME, get_current_user, require_roles
from app.core.errors import register_exception_handlers
from app.core.roles import Role
from app.core.security import create_access_token, create_refresh_token
from app.db.session import get_session
from app.models.base import Base
from app.models.user import User


@pytest.fixture
def sf() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite://", future=True, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False, future=True)
    engine.dispose()


@pytest.fixture
def app(sf: sessionmaker[Session]) -> FastAPI:
    application = FastAPI()
    register_exception_handlers(application)

    def _get_session() -> Iterator[Session]:
        s = sf()
        try:
            yield s
            s.commit()
        finally:
            s.close()

    application.dependency_overrides[get_session] = _get_session

    @application.get("/whoami")
    def _whoami(user: User = Depends(get_current_user)) -> dict[str, str]:
        return {"email": user.email}

    @application.get("/admin-only")
    def _admin(user: User = Depends(require_roles(Role.ADMIN))) -> dict[str, str]:
        return {"role": user.role.value}

    return application


@pytest.fixture
def make_user(sf: sessionmaker[Session]):
    def _make(email: str, role: Role, is_active: bool = True) -> int:
        with sf() as s:
            u = User(email=email, password_hash="h", role=role, is_active=is_active)
            s.add(u)
            s.commit()
            return u.id

    return _make


def test_missing_token_is_401(app: FastAPI) -> None:
    with TestClient(app) as c:
        assert c.get("/whoami").status_code == 401


def test_bearer_token_resolves_user(app: FastAPI, make_user) -> None:
    uid = make_user("pat@example.com", Role.PATIENT)
    token = create_access_token(str(uid), extra_claims={"role": "patient"})
    with TestClient(app) as c:
        r = c.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "pat@example.com"


def test_cookie_token_resolves_user(app: FastAPI, make_user) -> None:
    uid = make_user("pat@example.com", Role.PATIENT)
    token = create_access_token(str(uid))
    with TestClient(app) as c:
        c.cookies.set(SESSION_COOKIE_NAME, token)
        r = c.get("/whoami")
    assert r.status_code == 200


def test_refresh_token_rejected_as_access(app: FastAPI, make_user) -> None:
    uid = make_user("pat@example.com", Role.PATIENT)
    refresh = create_refresh_token(str(uid))
    with TestClient(app) as c:
        r = c.get("/whoami", headers={"Authorization": f"Bearer {refresh}"})
    assert r.status_code == 401


def test_deactivated_user_is_401(app: FastAPI, make_user) -> None:
    uid = make_user("gone@example.com", Role.PATIENT, is_active=False)
    token = create_access_token(str(uid))
    with TestClient(app) as c:
        r = c.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_require_roles_allows_and_denies(app: FastAPI, make_user) -> None:
    admin_id = make_user("admin@example.com", Role.ADMIN)
    patient_id = make_user("pat@example.com", Role.PATIENT)
    admin_tok = create_access_token(str(admin_id))
    patient_tok = create_access_token(str(patient_id))

    with TestClient(app) as c:
        ok = c.get("/admin-only", headers={"Authorization": f"Bearer {admin_tok}"})
        denied = c.get("/admin-only", headers={"Authorization": f"Bearer {patient_tok}"})

    assert ok.status_code == 200
    assert denied.status_code == 403
    assert denied.json()["code"] == "permission_denied"
