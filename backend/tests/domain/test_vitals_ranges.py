"""Unit tests for age-based vitals ranges (app.domain.vitals_ranges), §5.5."""

from __future__ import annotations

from app.domain.vitals_ranges import VitalsReading, flag_out_of_range


def test_all_in_range_for_adult_gives_no_flags() -> None:
    reading = VitalsReading(heart_rate=70, resp_rate=16, systolic_bp=120, temp_c=37.0, spo2=98)
    assert flag_out_of_range(40, reading) == []


def test_high_heart_rate_flagged_for_adult() -> None:
    assert "heart_rate_high" in flag_out_of_range(40, VitalsReading(heart_rate=130))


def test_same_reading_differs_by_age() -> None:
    """HR 150 is normal for an infant but high for an adult — the core §5.5 point."""
    infant = flag_out_of_range(0, VitalsReading(heart_rate=150))
    adult = flag_out_of_range(40, VitalsReading(heart_rate=150))
    assert infant == []
    assert adult == ["heart_rate_high"]


def test_low_and_high_directions() -> None:
    assert flag_out_of_range(40, VitalsReading(spo2=90)) == ["spo2_low"]
    assert flag_out_of_range(40, VitalsReading(temp_c=39.0)) == ["temp_c_high"]


def test_none_values_are_not_flagged() -> None:
    assert flag_out_of_range(40, VitalsReading()) == []


def test_multiple_flags_are_sorted() -> None:
    reading = VitalsReading(heart_rate=200, spo2=80)
    assert flag_out_of_range(40, reading) == ["heart_rate_high", "spo2_low"]


def test_child_band_applies() -> None:
    # HR 65 is below a child's band (70-120) but fine for an adult (60-100).
    assert flag_out_of_range(8, VitalsReading(heart_rate=65)) == ["heart_rate_low"]
    assert flag_out_of_range(40, VitalsReading(heart_rate=65)) == []
