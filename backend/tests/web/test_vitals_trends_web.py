"""Web test for the vitals-trends chart scaffold on the history page (M10).

Asserts the page loads the vendored Chart.js asset and includes the canvas
wired to the series endpoint. The chart itself renders client-side (Chart.js);
here we verify the server-rendered scaffolding and progressive-enhancement hook.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.roles import Role
from app.core.security import hash_password
from app.models.profile import PatientProfile
from app.models.user import User

PW = "longenough1"


@pytest.fixture
def patient(db_sessionmaker: sessionmaker[Session]) -> int:
    with db_sessionmaker() as s:
        pat = User(email="pat@example.com", password_hash=hash_password(PW), role=Role.PATIENT)
        s.add(pat)
        s.flush()
        s.add(PatientProfile(user_id=pat.id, date_of_birth=date(1986, 1, 1)))
        s.commit()
        return pat.id


def test_history_page_includes_vitals_chart_scaffold(
    client: TestClient, patient: int
) -> None:
    client.post("/login", data={"email": "pat@example.com", "password": PW})
    resp = client.get("/clinical/history")
    assert resp.status_code == 200
    body = resp.text
    assert "chart.umd.min.js" in body            # vendored Chart.js loaded
    assert 'id="vitals-chart"' in body           # canvas present
    assert f"/api/v1/patients/{patient}/vitals-series" in body  # wired to data endpoint
