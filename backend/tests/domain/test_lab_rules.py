"""Unit tests for lab result flagging (app.domain.lab_rules), M8."""

from __future__ import annotations

from app.domain.lab_rules import is_abnormal


def test_within_range_is_normal() -> None:
    assert is_abnormal(7.0, 4.0, 11.0) is False


def test_below_low_is_abnormal() -> None:
    assert is_abnormal(3.0, 4.0, 11.0) is True


def test_above_high_is_abnormal() -> None:
    assert is_abnormal(12.0, 4.0, 11.0) is True


def test_bounds_are_inclusive() -> None:
    assert is_abnormal(4.0, 4.0, 11.0) is False
    assert is_abnormal(11.0, 4.0, 11.0) is False


def test_open_ended_low() -> None:
    # No lower limit: only a high breach is abnormal.
    assert is_abnormal(0.0, None, 11.0) is False
    assert is_abnormal(12.0, None, 11.0) is True


def test_open_ended_high() -> None:
    assert is_abnormal(999.0, 4.0, None) is False
    assert is_abnormal(1.0, 4.0, None) is True


def test_no_range_is_normal() -> None:
    assert is_abnormal(42.0, None, None) is False
