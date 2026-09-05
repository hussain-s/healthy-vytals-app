"""Prescription safety rules (§5.4) — pure decision logic.

Three checks run before a drug is prescribed (DESIGN §5.4). They differ in
*severity*, which is the non-obvious part an AI can't infer from a schema:

    1. **Allergy → HARD BLOCK.** If the drug (by name) or its class matches a
       recorded patient allergy, prescribing is refused outright. There is no
       override — prescribing into a known allergy is never acceptable.
    2. **Drug interaction → WARN (overridable).** If the drug interacts with one
       of the patient's active medications, prescribing is blocked *unless* the
       prescriber explicitly overrides, acknowledging the risk. Clinicians
       routinely co-prescribe interacting drugs with monitoring, so this is a
       speed bump, not a wall.
    3. **Controlled substance → REFILL CAP.** A controlled substance may not be
       prescribed with more than the allowed number of refills.

This module takes plain value objects (what the patient is allergic to, their
active meds, the interaction set, the candidate drug) and returns a decision. It
does no I/O; the service supplies the facts from repositories and turns a blocked
decision into the right typed error.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Controlled substances cap refills at this count (§5.4). Kept as a named
# constant so the rule is visible and testable, not a magic number.
MAX_CONTROLLED_REFILLS = 0


@dataclass(frozen=True)
class DrugFacts:
    """The candidate medication being prescribed."""

    medication_id: int
    name: str
    drug_class: str | None
    is_controlled: bool


@dataclass(frozen=True)
class SafetyContext:
    """Everything the checks need about the patient, gathered by the service.

    * ``allergy_terms`` — lower-cased substance/class names the patient is
      allergic to (drug name OR class).
    * ``interacting_medication_ids`` — the patient's *active* medication ids that
      interact with the candidate drug (precomputed by the service from the
      DrugInteraction table). Non-empty means an interaction is present.
    """

    allergy_terms: frozenset[str] = field(default_factory=frozenset)
    interacting_medication_ids: frozenset[int] = field(default_factory=frozenset)


@dataclass(frozen=True)
class SafetyResult:
    """Outcome of the safety evaluation.

    ``allowed`` is the final go/no-go. ``block_reason`` is a stable code when
    blocked (``allergy`` | ``interaction`` | ``refill_cap``); ``warnings`` carries
    non-blocking advisories. When an interaction is present, the result is blocked
    with reason ``interaction`` unless ``override`` was passed.
    """

    allowed: bool
    block_reason: str | None = None
    message: str | None = None
    warnings: tuple[str, ...] = ()


def evaluate_prescription(
    drug: DrugFacts,
    context: SafetyContext,
    *,
    refills: int,
    override_interaction: bool = False,
) -> SafetyResult:
    """Evaluate the three §5.4 checks and return a :class:`SafetyResult`.

    Order matters: allergy is checked first (hard block, non-overridable), then
    the controlled-substance refill cap, then interactions (overridable). This
    ordering means an allergy is always reported even if other issues exist, and
    an override can never bypass an allergy.
    """
    # 1. Allergy — hard block (name or class match), no override.
    candidate_terms = {drug.name.lower()}
    if drug.drug_class:
        candidate_terms.add(drug.drug_class.lower())
    if candidate_terms & context.allergy_terms:
        return SafetyResult(
            allowed=False,
            block_reason="allergy",
            message=f"Patient has a recorded allergy to {drug.name} or its class",
        )

    # 2. Controlled-substance refill cap.
    if drug.is_controlled and refills > MAX_CONTROLLED_REFILLS:
        return SafetyResult(
            allowed=False,
            block_reason="refill_cap",
            message=(
                f"{drug.name} is a controlled substance; refills may not exceed "
                f"{MAX_CONTROLLED_REFILLS}"
            ),
        )

    # 3. Drug interaction — warn, overridable.
    if context.interacting_medication_ids:
        warning = f"{drug.name} interacts with one of the patient's active medications"
        if not override_interaction:
            return SafetyResult(
                allowed=False,
                block_reason="interaction",
                message=warning + " (override required to proceed)",
                warnings=(warning,),
            )
        # Overridden: allowed, but the warning is surfaced for the record.
        return SafetyResult(allowed=True, warnings=(warning,))

    return SafetyResult(allowed=True)
