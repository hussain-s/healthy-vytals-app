"""Vitals triage assistant — the app's first AI-assisted use case (DESIGN §14).

This service turns a set of recorded vitals into a short, structured,
plain-language read for staff (a :class:`VitalsAssessment`). It is the worked
example the book builds Chapter 2 around: it shows an LLM wired into a real app
*as a system component*, not a chatbot.

Two principles govern it, and they are the point of the design:

1. **The deterministic rule is the source of truth; the model only explains it.**
   ``domain/vitals_ranges.flag_out_of_range`` (Rule #5, pure, unit-tested) computes
   the authoritative out-of-range flags. We pass those *into* the prompt and ask
   the model to explain and prioritize them in plain language. The model never
   sets thresholds, so it cannot silently disagree with the clinical rule. Because
   those flags are ground truth, they are also the label the book's later
   evaluation/calibration chapters score the model against.
2. **Decision-support, human-in-the-loop — never diagnosis.** The output is an
   advisory summary for a nurse/doctor who decides. This honors the app's
   Non-Goals ("not medical advice") and the responsible-AI posture: an AI in the
   loop, a human at the center.

Reliability & safety come from the component layer (``core/llm``): retries,
fallback, timeout, caching, and structured-output validation. On top of that, this
service adds a **safe degradation** path — if the model refuses or errors, we
still return a useful rules-only assessment built from the deterministic flags,
rather than failing the caller. Every invocation is audited (Rule #7) with an
``llm.*`` action so AI use is as accountable as any other PHI touch.

Layering (ADR-0004): this is a service. It calls the pure domain function and the
``core/llm`` client; it does not touch the DB directly (the optional ``session``
is only used to write an audit row via ``audit_service``).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import NotFound, PermissionDenied
from app.core.llm.client import LLMClient
from app.core.llm.errors import LLMError
from app.core.llm.vitals_schema import Urgency, VitalsAssessment
from app.core.roles import Role
from app.domain.vitals_ranges import VitalsReading, flag_out_of_range
from app.models.user import User
from app.repositories.encounter_repository import EncounterRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_service import record_audit

# System prompt: fixes the model's role and the hard guardrail (explain, don't
# diagnose; defer to the flags). Kept here, versioned with the code.
_SYSTEM = (
    "You are a clinical-support assistant for triage nurses. You explain recorded "
    "vital signs in plain language to help staff prioritize. You DO NOT diagnose, "
    "prescribe, or invent normal ranges: the provided out-of-range flags are "
    "authoritative and computed by a validated clinical rule. Explain and "
    "prioritize those flags; never contradict them. A human clinician always decides."
)


def _rules_only_assessment(
    age_years: int, reading: VitalsReading, flags: list[str]
) -> VitalsAssessment:
    """Build a useful assessment from the deterministic flags alone (no model).

    Used both as the *degraded* path when the LLM is unavailable/refuses and as a
    guaranteed floor of quality. Urgency is a simple, transparent function of how
    many values are abnormal — never worse than the model would be, and fully
    explainable. ``confidence`` is 1.0 because these flags are ground truth.
    """
    if not flags:
        return VitalsAssessment(
            summary="All recorded vitals are within the age-normal range.",
            urgency=Urgency.ROUTINE,
            red_flags=[],
            recommended_action="Proceed with the normal workflow.",
            confidence=1.0,
        )
    urgency = Urgency.ELEVATED if len(flags) < 3 else Urgency.URGENT
    pretty = [f.replace("_", " ") for f in flags]
    return VitalsAssessment(
        summary=(
            f"{len(flags)} recorded value(s) are outside the age-normal range: "
            f"{', '.join(pretty)}."
        ),
        urgency=urgency,
        red_flags=pretty,
        recommended_action="Review the flagged vitals with the attending clinician.",
        confidence=1.0,
    )


def assess_vitals(
    age_years: int,
    reading: VitalsReading,
    *,
    client: LLMClient | None = None,
    session: Session | None = None,
    actor_id: int | None = None,
    patient_id: int | None = None,
) -> VitalsAssessment:
    """Return a structured, plain-language assessment of a set of vitals.

    ``age_years`` and ``reading`` are the clinical inputs. ``client`` is injectable
    for tests (defaults to a process client using the configured provider — the
    offline stub unless a real provider is configured). If ``session`` is given,
    the call is audited (Rule #7).

    Flow: compute authoritative flags → ask the model to explain them under the
    guardrail system prompt → on any LLM failure, **degrade** to the rules-only
    assessment. Either way the caller gets a valid :class:`VitalsAssessment`.
    """
    flags = flag_out_of_range(age_years, reading)
    client = client or LLMClient()

    content = (
        f"Patient age (years): {age_years}\n"
        f"Recorded vitals: heart_rate={reading.heart_rate}, "
        f"resp_rate={reading.resp_rate}, systolic_bp={reading.systolic_bp}, "
        f"temp_c={reading.temp_c}, spo2={reading.spo2}\n"
        f"Authoritative out-of-range flags (from the clinical rule; do not "
        f"contradict): {flags or 'none'}"
    )

    action = "llm.vitals_assessed"
    degraded = False
    try:
        assessment = client.analyze(
            content,
            VitalsAssessment,
            tier="reasoning",
            system=_SYSTEM,
            instruction=(
                "Explain these vitals for a triage nurse and prioritize the flags."
            ),
        )
    except LLMError:
        # Safe degradation: the model is unavailable or produced nothing usable.
        # Fall back to the deterministic flags so the caller is never blocked.
        assessment = _rules_only_assessment(age_years, reading, flags)
        action = "llm.vitals_assessed_degraded"
        degraded = True

    if session is not None:
        record_audit(
            session,
            action=action,
            actor_id=actor_id,
            resource_type="vitals_assessment",
            patient_id=patient_id,
        )

    # A model must not downgrade a rule-detected abnormality to "routine": the
    # deterministic flags win. This is a safety clamp, not a style choice.
    if flags and assessment.urgency is Urgency.ROUTINE and not degraded:
        assessment = assessment.model_copy(update={"urgency": Urgency.ELEVATED})

    return assessment


def _age_years(dob: date | None, on: datetime) -> int:
    """Whole years from ``dob`` to ``on``; adult (40) when unknown.

    Mirrors ``clinical_service._age_years`` (the vitals rule's age source, §5.5);
    duplicated as a small private helper to avoid a service→service import.
    """
    if dob is None:
        return 40
    years = on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))
    return max(0, years)


def assess_encounter_vitals(
    session: Session,
    *,
    staff: User,
    encounter_id: int,
    client: LLMClient | None = None,
) -> VitalsAssessment:
    """Assess the **latest recorded vitals** for an encounter, for API/web callers.

    This is the entry point the endpoint and the nurse UI use. It resolves the
    patient's age and most-recent reading from the encounter, applies the same
    authorization as reading history, then delegates to :func:`assess_vitals`
    (which composes the ground-truth flags with the model and audits the call).

    Authorization mirrors clinical access (§5.3): a nurse may assess any patient's
    triage vitals; a doctor needs a treating relationship with the patient; anyone
    else is denied. Raises :class:`NotFound` if the encounter or a reading is
    missing, :class:`PermissionDenied` if the caller may not view this patient.
    """
    repo = EncounterRepository(session)
    encounter = repo.get(encounter_id)
    if encounter is None:
        raise NotFound(f"No such encounter: {encounter_id}")

    # Coarse role gate is done at the router; here we enforce the fine-grained
    # treating-relationship rule for doctors (nurses are permitted triage-wide).
    if staff.role is Role.DOCTOR and not repo.has_treating_relationship(
        staff.id, encounter.patient_id
    ):
        record_audit(
            session,
            action="llm.vitals_assessed_denied",
            actor_id=staff.id,
            resource_type="encounter",
            resource_id=encounter_id,
            patient_id=encounter.patient_id,
            commit=True,  # survives the raise below (mirrors history read-deny)
        )
        raise PermissionDenied("No treating relationship with this patient")
    if staff.role not in (Role.NURSE, Role.DOCTOR):
        raise PermissionDenied("Only clinical staff may request a vitals assessment")

    readings = repo.vitals_for_encounter(encounter_id)
    if not readings:
        raise NotFound("No vitals recorded for this encounter yet")
    latest = readings[-1]
    reading = VitalsReading(
        heart_rate=latest.heart_rate,
        resp_rate=latest.resp_rate,
        systolic_bp=latest.systolic_bp,
        temp_c=latest.temp_c,
        spo2=latest.spo2,
    )

    profile = UserRepository(session).get_patient_profile(encounter.patient_id)
    dob = profile.date_of_birth if profile is not None else None
    age = _age_years(dob, datetime.now(timezone.utc))

    return assess_vitals(
        age,
        reading,
        client=client,
        session=session,
        actor_id=staff.id,
        patient_id=encounter.patient_id,
    )
