"""Scheduling rules — slot conflict/buffer and cancellation cutoff (§5.2).

Pure domain logic operating on plain datetimes and small value objects; it knows
nothing about the ORM or HTTP. Services pass in the relevant times (loaded via
repositories) and act on the decisions returned here.

Two rules from DESIGN §5.2:

    1. **Conflict + buffer** — a doctor cannot have two appointments that overlap,
       and a configurable buffer must separate consecutive appointments. We treat
       each existing appointment as if it were widened by the buffer on both
       sides, then test for overlap against the candidate window. Slots are
       half-open ``[start, end)``, so touching endpoints do not overlap.

    2. **Cancellation cutoff** — a cancellation is always *allowed*, but if it
       happens within the cutoff window before the appointment start it is flagged
       **late** (for later policy, e.g. a fee). We return the flag rather than
       blocking, mirroring the rule's intent.

Thresholds (buffer minutes, cutoff hours) are passed in by the caller, which
reads them from ``Settings`` — the domain does not reach into config itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class TimeWindow:
    """A half-open time interval ``[start, end)``. Immutable value object."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("TimeWindow end must be after start")


def windows_overlap(a: TimeWindow, b: TimeWindow) -> bool:
    """Return whether two half-open windows overlap.

    Half-open semantics: ``[9:00, 9:30)`` and ``[9:30, 10:00)`` do **not** overlap,
    so back-to-back appointments are allowed (before buffer is applied).
    """
    return a.start < b.end and b.start < a.end


def conflicts_with_buffer(
    candidate: TimeWindow,
    existing: list[TimeWindow],
    buffer_minutes: int,
) -> bool:
    """Return whether ``candidate`` conflicts with any ``existing`` window.

    Each existing window is expanded by ``buffer_minutes`` on both sides before
    the overlap test, enforcing a minimum gap between appointments. A zero buffer
    reduces this to a pure overlap check.
    """
    buffer = timedelta(minutes=buffer_minutes)
    for window in existing:
        padded = TimeWindow(start=window.start - buffer, end=window.end + buffer)
        if windows_overlap(candidate, padded):
            return True
    return False


def is_late_cancellation(
    now: datetime, appointment_start: datetime, cutoff_hours: int
) -> bool:
    """Return whether cancelling ``now`` is within the late-cancellation window.

    True when the appointment starts sooner than ``cutoff_hours`` from now (or has
    already started). The caller decides what a late flag means; this function only
    classifies. A cancellation is never *blocked* by this rule (§5.2).
    """
    cutoff = timedelta(hours=cutoff_hours)
    return appointment_start - now < cutoff
