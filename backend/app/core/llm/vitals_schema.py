"""Output contract for the vitals triage assistant (DESIGN §14, Rule #11).

This is the structured shape the LLM must return when explaining a set of vitals.
It lives beside the LLM layer because it is a *model output contract*, not an HTTP
wire schema (those stay in ``schemas/``). The service maps this to a response
model before it reaches a client.

Design intent (decision-support, human-in-the-loop — NOT diagnosis):
* The deterministic, age-based flags from ``domain/vitals_ranges.flag_out_of_range``
  remain the **source of truth**; this assistant only *explains and prioritizes*
  them in plain language. That is why the service passes the computed flags in and
  the model is instructed to explain them, never to invent thresholds.
* ``confidence`` and ``red_flags`` are first-class so later chapters can calibrate
  and evaluate them; ``recommended_action`` is intentionally a small closed set so
  downstream code and the UI can branch on it reliably (contracts, discipline 1).
"""

from __future__ import annotations

import enum

from pydantic import Field

from app.core.llm.schemas import AssistantSchema


class Urgency(str, enum.Enum):
    """How soon a clinician should look, as judged from the vitals + flags.

    A closed set (not free text) so the UI and any triage queue can sort/branch on
    it deterministically. This is an operational hint for staff, not a diagnosis.
    """

    ROUTINE = "routine"        # nothing abnormal; normal workflow
    ELEVATED = "elevated"      # some abnormal values; review during the visit
    URGENT = "urgent"          # concerning combination; review promptly
    IMMEDIATE = "immediate"    # potentially life-threatening pattern; see now


class VitalsAssessment(AssistantSchema):
    """A structured, plain-language read of a patient's vitals for staff.

    Produced by the LLM from the patient's age, the recorded readings, and the
    deterministic out-of-range flags. Every field is validated before a caller
    sees it, so the service never handles half-formed output.
    """

    summary: str = Field(
        description="One or two plain-language sentences a nurse can read at a "
        "glance, explaining what the recorded vitals suggest. No diagnosis.",
    )
    urgency: Urgency = Field(
        description="How soon a clinician should review, given the readings and flags.",
    )
    red_flags: list[str] = Field(
        default_factory=list,
        description="Short phrases naming the specific concerning findings "
        "(e.g. 'low oxygen saturation'). Empty if nothing is concerning.",
    )
    recommended_action: str = Field(
        description="One short next step for staff (e.g. 'recheck SpO2 and notify "
        "the attending'). Advisory only; a human decides.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="The model's self-reported confidence in this assessment, 0..1. "
        "Advisory; not calibrated here (see book Ch. on evaluation).",
    )
