"""Phase 1 exit-gate integration test: RBAC + audit end to end.

Pins the Phase 1 acceptance criteria as one story (DESIGN §9 Phase 1 exit):
    * all four roles can log in and resolve via /me;
    * a forbidden action returns 403 (patient hitting the admin-only endpoint);
    * PHI/security actions leave audit rows.

Staff accounts are provisioned by an admin (not self-service), exactly as a real
operator would set up the clinic, so this also exercises the provisioning path.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.models.audit import AuditLog
from app.models.user import User

DEMO_PW = "longenough1"


@pytest.fixture
def bootstrap_admin(db_sessionmaker: sessionmaker[Session]) -> None:
    """Seed a single admin directly (the clinic's first account)."""
    with db_sessionmaker() as s:
        s.add(
            User(
                email="admin@example.com",
                password_hash=hash_password(DEMO_PW),
                role=Role.ADMIN,
            )
        )
        s.commit()


def _login(client: TestClient, email: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": DEMO_PW})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_phase1_exit_gate(
    client: TestClient,
    bootstrap_admin: None,
    db_sessionmaker: sessionmaker[Session],
) -> None:
    # 1. Admin logs in and provisions the clinical staff (doctor, nurse).
    admin_token = _login(client, "admin@example.com")
    for email, role in [("doctor@example.com", "doctor"), ("nurse@example.com", "nurse")]:
        created = client.post(
            "/api/v1/users",
            headers=_auth(admin_token),
            json={"email": email, "password": DEMO_PW, "role": role},
        )
        assert created.status_code == 201

    # A patient self-registers.
    assert client.post(
        "/api/v1/auth/register", json={"email": "patient@example.com", "password": DEMO_PW}
    ).status_code == 201

    # 2. All four roles can log in and resolve their identity via /me.
    for email, expected_role in [
        ("admin@example.com", "admin"),
        ("doctor@example.com", "doctor"),
        ("nurse@example.com", "nurse"),
        ("patient@example.com", "patient"),
    ]:
        token = _login(client, email)
        me = client.get("/api/v1/auth/me", headers=_auth(token))
        assert me.status_code == 200
        assert me.json()["role"] == expected_role

    # 3. A forbidden action returns 403 (patient may not provision staff).
    patient_token = _login(client, "patient@example.com")
    forbidden = client.post(
        "/api/v1/users",
        headers=_auth(patient_token),
        json={"email": "sneaky@example.com", "password": DEMO_PW, "role": "doctor"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "permission_denied"

    # 4. Audit rows exist for the security-relevant actions we performed.
    with db_sessionmaker() as s:
        actions = set(s.scalars(select(AuditLog.action)).all())
    assert {"user.provision", "user.register", "auth.login"} <= actions


def test_failed_login_is_audited_without_actor(
    client: TestClient,
    bootstrap_admin: None,
    db_sessionmaker: sessionmaker[Session],
) -> None:
    """A login with an unknown email records an auth.login_failed row (no actor)."""
    resp = client.post(
        "/api/v1/auth/login", json={"email": "ghost@example.com", "password": DEMO_PW}
    )
    assert resp.status_code == 401

    with db_sessionmaker() as s:
        failed = s.scalars(
            select(AuditLog).where(AuditLog.action == "auth.login_failed")
        ).all()
    assert len(failed) == 1
    assert failed[0].actor_id is None
