"""Unit tests for prescription safety (app.domain.prescription_safety), §5.4."""

from __future__ import annotations

from app.domain.prescription_safety import (
    MAX_CONTROLLED_REFILLS,
    DrugFacts,
    SafetyContext,
    evaluate_prescription,
)

AMOX = DrugFacts(medication_id=1, name="Amoxicillin", drug_class="penicillin", is_controlled=False)
OXY = DrugFacts(medication_id=2, name="Oxycodone", drug_class="opioid", is_controlled=True)


def test_clean_prescription_allowed() -> None:
    result = evaluate_prescription(AMOX, SafetyContext(), refills=2)
    assert result.allowed is True
    assert result.block_reason is None


def test_allergy_by_name_hard_blocks() -> None:
    ctx = SafetyContext(allergy_terms=frozenset({"amoxicillin"}))
    result = evaluate_prescription(AMOX, ctx, refills=0)
    assert result.allowed is False
    assert result.block_reason == "allergy"


def test_allergy_by_class_hard_blocks() -> None:
    ctx = SafetyContext(allergy_terms=frozenset({"penicillin"}))
    result = evaluate_prescription(AMOX, ctx, refills=0)
    assert result.allowed is False
    assert result.block_reason == "allergy"


def test_allergy_cannot_be_overridden() -> None:
    """Even with override, an allergy match is refused (non-overridable)."""
    ctx = SafetyContext(allergy_terms=frozenset({"amoxicillin"}))
    result = evaluate_prescription(AMOX, ctx, refills=0, override_interaction=True)
    assert result.allowed is False
    assert result.block_reason == "allergy"


def test_controlled_substance_refill_cap() -> None:
    result = evaluate_prescription(OXY, SafetyContext(), refills=MAX_CONTROLLED_REFILLS + 1)
    assert result.allowed is False
    assert result.block_reason == "refill_cap"


def test_controlled_substance_within_cap_allowed() -> None:
    result = evaluate_prescription(OXY, SafetyContext(), refills=MAX_CONTROLLED_REFILLS)
    assert result.allowed is True


def test_interaction_blocks_without_override() -> None:
    ctx = SafetyContext(interacting_medication_ids=frozenset({99}))
    result = evaluate_prescription(AMOX, ctx, refills=0)
    assert result.allowed is False
    assert result.block_reason == "interaction"
    assert result.warnings


def test_interaction_allowed_with_override_but_warns() -> None:
    ctx = SafetyContext(interacting_medication_ids=frozenset({99}))
    result = evaluate_prescription(AMOX, ctx, refills=0, override_interaction=True)
    assert result.allowed is True
    assert result.warnings  # the risk is still surfaced for the record


def test_allergy_takes_precedence_over_interaction() -> None:
    """Allergy is checked first, so it's reported even if an interaction exists."""
    ctx = SafetyContext(
        allergy_terms=frozenset({"amoxicillin"}),
        interacting_medication_ids=frozenset({99}),
    )
    result = evaluate_prescription(AMOX, ctx, refills=0, override_interaction=True)
    assert result.block_reason == "allergy"
