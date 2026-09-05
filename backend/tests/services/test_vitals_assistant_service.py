"""Tests for the vitals triage assistant service (DESIGN §14).

Offline: an injected fake ``LLMClient``-shaped stub or the default deterministic
stub provider is used, so no API key/SDK is needed. Focus is on the *composition*
rules the service adds on top of the component layer: ground-truth flags win,
safe degradation on LLM failure, the urgency clamp, and auditing.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.llm.client import LLMClient
from app.core.llm.errors import LLMRefusal
from app.core.llm.providers import ProviderResult, StubProvider
from app.core.llm.vitals_schema import Urgency, VitalsAssessment
from app.domain.vitals_ranges import VitalsReading
from app.models.audit import AuditLog
from app.models.base import Base
from app.services import vitals_assistant_service as svc


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False, future=True)() as s:
        yield s
    engine.dispose()


def _stub_client(**kw) -> LLMClient:
    kw.setdefault("sleep", lambda _s: None)
    return LLMClient(provider=StubProvider(), enable_cache=False, **kw)


class _RefusingProvider:
    def complete(self, **kwargs) -> ProviderResult:
        return ProviderResult(text="", is_refusal=True)


def test_returns_valid_assessment_from_stub() -> None:
    """Happy path: a schema-valid assessment comes back offline via the stub."""
    reading = VitalsReading(heart_rate=80, spo2=98, temp_c=37.0)
    out = svc.assess_vitals(40, reading, client=_stub_client())
    assert isinstance(out, VitalsAssessment)
    assert 0.0 <= out.confidence <= 1.0


def test_degrades_to_rules_only_on_refusal() -> None:
    """If the model refuses, we still return a useful rules-based assessment."""
    client = LLMClient(
        provider=_RefusingProvider(), enable_cache=False, sleep=lambda _s: None
    )
    # An adult SpO2 of 88 is below the normal band → a real flag exists.
    reading = VitalsReading(spo2=88)
    out = svc.assess_vitals(40, reading, client=client)
    assert out.urgency is not Urgency.ROUTINE
    assert out.red_flags  # names the abnormal finding
    assert out.confidence == 1.0  # rules-only path is ground truth


def test_no_flags_gives_routine_when_degraded() -> None:
    """Rules-only path with all-normal vitals is a clean 'routine'."""
    client = LLMClient(
        provider=_RefusingProvider(), enable_cache=False, sleep=lambda _s: None
    )
    out = svc.assess_vitals(40, VitalsReading(heart_rate=72, spo2=98), client=client)
    assert out.urgency is Urgency.ROUTINE
    assert out.red_flags == []


def test_model_cannot_downgrade_a_flagged_reading_to_routine() -> None:
    """Safety clamp: with a real flag, a model 'routine' is bumped to elevated."""

    class _RoutineProvider:
        def complete(self, **kwargs) -> ProviderResult:
            return ProviderResult(
                text=(
                    '{"summary":"looks fine","urgency":"routine","red_flags":[],'
                    '"recommended_action":"proceed","confidence":0.9}'
                )
            )

    client = LLMClient(
        provider=_RoutineProvider(), enable_cache=False, sleep=lambda _s: None
    )
    reading = VitalsReading(spo2=85)  # clearly abnormal for an adult
    out = svc.assess_vitals(40, reading, client=client)
    assert out.urgency is Urgency.ELEVATED  # clamped up from the model's "routine"


def test_audits_when_session_provided(session: Session) -> None:
    """A successful assessment writes an llm.vitals_assessed audit row (Rule #7)."""
    svc.assess_vitals(
        40,
        VitalsReading(heart_rate=80),
        client=_stub_client(),
        session=session,
        actor_id=7,
        patient_id=42,
    )
    rows = session.scalars(select(AuditLog)).all()
    assert len(rows) == 1
    assert rows[0].action == "llm.vitals_assessed"
    assert rows[0].patient_id == 42 and rows[0].actor_id == 7


def test_audits_degraded_action_distinctly(session: Session) -> None:
    """The degraded path records a distinct action so ops can see fallbacks."""
    client = LLMClient(
        provider=_RefusingProvider(), enable_cache=False, sleep=lambda _s: None
    )
    svc.assess_vitals(
        40, VitalsReading(spo2=88), client=client, session=session, patient_id=1
    )
    row = session.scalars(select(AuditLog)).one()
    assert row.action == "llm.vitals_assessed_degraded"
