"""Unit tests for scheduling rules (app.domain.scheduling_rules), §5.2.

Pure tests over datetimes: overlap semantics, buffer enforcement, and the
late-cancellation classification.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.scheduling_rules import (
    TimeWindow,
    conflicts_with_buffer,
    is_late_cancellation,
    windows_overlap,
)

BASE = datetime(2026, 9, 1, 9, 0, tzinfo=timezone.utc)


def _w(start_min: int, end_min: int) -> TimeWindow:
    return TimeWindow(start=BASE + timedelta(minutes=start_min), end=BASE + timedelta(minutes=end_min))


def test_time_window_rejects_non_positive_duration() -> None:
    with pytest.raises(ValueError):
        TimeWindow(start=BASE, end=BASE)


def test_overlapping_windows() -> None:
    assert windows_overlap(_w(0, 30), _w(15, 45)) is True


def test_back_to_back_windows_do_not_overlap() -> None:
    """Half-open [9:00,9:30) and [9:30,10:00) touch but do not overlap."""
    assert windows_overlap(_w(0, 30), _w(30, 60)) is False


def test_no_conflict_when_gap_exceeds_buffer() -> None:
    candidate = _w(60, 90)  # 10:00–10:30
    existing = [_w(0, 30)]  # 09:00–09:30, 30 min before → fine with 10-min buffer
    assert conflicts_with_buffer(candidate, existing, buffer_minutes=10) is False


def test_conflict_when_within_buffer() -> None:
    """A 10-min buffer makes a slot starting 5 min after another conflict."""
    candidate = _w(35, 65)  # starts 5 min after existing ends
    existing = [_w(0, 30)]
    assert conflicts_with_buffer(candidate, existing, buffer_minutes=10) is True


def test_direct_overlap_is_a_conflict_regardless_of_buffer() -> None:
    candidate = _w(15, 45)
    existing = [_w(0, 30)]
    assert conflicts_with_buffer(candidate, existing, buffer_minutes=0) is True


def test_no_existing_means_no_conflict() -> None:
    assert conflicts_with_buffer(_w(0, 30), [], buffer_minutes=10) is False


def test_conflict_checks_all_existing_windows() -> None:
    candidate = _w(200, 230)
    existing = [_w(0, 30), _w(205, 235), _w(400, 430)]  # middle one overlaps
    assert conflicts_with_buffer(candidate, existing, buffer_minutes=0) is True


def test_late_cancellation_within_cutoff() -> None:
    now = BASE
    start = BASE + timedelta(hours=12)  # 12h away, cutoff 24h → late
    assert is_late_cancellation(now, start, cutoff_hours=24) is True


def test_not_late_when_outside_cutoff() -> None:
    now = BASE
    start = BASE + timedelta(hours=48)  # 48h away, cutoff 24h → not late
    assert is_late_cancellation(now, start, cutoff_hours=24) is False


def test_already_started_is_late() -> None:
    now = BASE
    start = BASE - timedelta(minutes=5)  # already began
    assert is_late_cancellation(now, start, cutoff_hours=24) is True
