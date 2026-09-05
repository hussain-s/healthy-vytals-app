"""Lab result rules (v2 M8) — pure abnormal-flagging logic.

A recorded lab value is *abnormal* when it falls outside its reference range.
Ranges are per-analyte and supplied with the reading (the ordering system knows
the panel's expected ranges); this module just applies the comparison, so the
rule is unit-testable without a DB and documented in the KB.

Like the vitals ranges (§5.5), the reference values used in seeds are illustrative
teaching values, not medical advice (DESIGN Non-Goals). The point is a clear,
explainable rule an AI can reason about.
"""

from __future__ import annotations


def is_abnormal(
    value: float,
    reference_low: float | None,
    reference_high: float | None,
) -> bool:
    """Return whether ``value`` is outside the [low, high] reference range.

    Either bound may be ``None`` (open-ended): a missing low means "no lower
    limit", a missing high means "no upper limit". With both ``None`` the value is
    always considered normal (no range to violate). Bounds are inclusive.
    """
    if reference_low is not None and value < reference_low:
        return True
    if reference_high is not None and value > reference_high:
        return True
    return False
