"""Vitals normal ranges and out-of-range flagging (§5.5) — pure domain logic.

Normal physiological ranges vary by **age** (an infant's normal heart rate is far
higher than an adult's), so a fixed threshold would misflag children. This module
holds the age-banded reference ranges and a pure function that, given a patient's
age and a set of readings, returns the list of flags for values outside their
normal band. Services attach those flags to the encounter so out-of-range visits
surface for attention.

Nothing here touches the DB or HTTP; it operates on plain numbers and returns
plain data, so the (clinically important) thresholds are unit-testable in
isolation and documented in the knowledge base.

The reference values are illustrative teaching values, **not** medical advice
(DESIGN Non-Goals): the point is to demonstrate an age-dependent rule an AI could
not infer from a schema.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VitalsReading:
    """A set of vitals measurements. Any field may be ``None`` (not recorded)."""

    heart_rate: int | None = None          # beats per minute
    resp_rate: int | None = None           # breaths per minute
    systolic_bp: int | None = None         # mmHg
    temp_c: float | None = None            # Celsius
    spo2: int | None = None                # % oxygen saturation


@dataclass(frozen=True)
class _Band:
    """Inclusive normal range [low, high] for a single measurement."""

    low: float
    high: float


@dataclass(frozen=True)
class _AgeRanges:
    """Normal bands for each measurement in one age group."""

    heart_rate: _Band
    resp_rate: _Band
    systolic_bp: _Band
    temp_c: _Band
    spo2: _Band


# Age-banded reference ranges. Ordered; the first band whose max_age covers the
# patient's age applies. Temperature and SpO2 bands are age-independent in this
# simplified model, but heart/resp/BP vary strongly with age.
_AGE_BANDS: list[tuple[int, _AgeRanges]] = [
    # max_age (inclusive), ranges
    (1, _AgeRanges(_Band(100, 160), _Band(30, 60), _Band(70, 100), _Band(36.5, 37.5), _Band(95, 100))),   # infant
    (12, _AgeRanges(_Band(70, 120), _Band(18, 30), _Band(90, 120), _Band(36.5, 37.5), _Band(95, 100))),   # child
    (17, _AgeRanges(_Band(60, 100), _Band(12, 20), _Band(100, 130), _Band(36.5, 37.5), _Band(95, 100))),  # adolescent
    (200, _AgeRanges(_Band(60, 100), _Band(12, 20), _Band(90, 140), _Band(36.0, 37.5), _Band(94, 100))),  # adult+
]


def _ranges_for_age(age_years: int) -> _AgeRanges:
    """Return the normal ranges applicable to a patient of the given age."""
    for max_age, ranges in _AGE_BANDS:
        if age_years <= max_age:
            return ranges
    return _AGE_BANDS[-1][1]  # fallback to adult (unreachable given max_age=200)


def flag_out_of_range(age_years: int, reading: VitalsReading) -> list[str]:
    """Return sorted flags for each recorded value outside its age-normal band.

    Only recorded (non-``None``) measurements are checked. A flag names the
    measurement and the direction, e.g. ``"heart_rate_high"`` or ``"spo2_low"``,
    so the encounter can surface exactly what is abnormal. An empty list means all
    recorded vitals are within range.
    """
    ranges = _ranges_for_age(age_years)
    checks: list[tuple[str, float | None, _Band]] = [
        ("heart_rate", reading.heart_rate, ranges.heart_rate),
        ("resp_rate", reading.resp_rate, ranges.resp_rate),
        ("systolic_bp", reading.systolic_bp, ranges.systolic_bp),
        ("temp_c", reading.temp_c, ranges.temp_c),
        ("spo2", reading.spo2, ranges.spo2),
    ]
    flags: list[str] = []
    for name, value, band in checks:
        if value is None:
            continue
        if value < band.low:
            flags.append(f"{name}_low")
        elif value > band.high:
            flags.append(f"{name}_high")
    return sorted(flags)
