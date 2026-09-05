"""Lab order and result models (v2 M8).

Models the lab workflow (DESIGN §13.2): a doctor places a :class:`LabOrder` on an
encounter; a nurse/lab records one or more :class:`LabResult` rows against it; the
patient and treating doctor view results, with out-of-range values flagged.

Append-only, consistent with the other clinical records (§5.6, ADR-0002):
    * an order moves through a small status lifecycle (ordered → resulted /
      cancelled) but is never deleted;
    * results are immutable once recorded — a correction is a new result row (or
      an Addendum), never an in-place edit.

Result visibility reuses the treating-relationship scoping (§5.3) + consent
(§5.8) already applied to encounter history; enforcement lives in the service.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class LabOrder(IdMixin, TimestampMixin, Base):
    """A lab test a doctor orders on an encounter.

    ``test_code``/``test_name`` identify the panel (a curated string, not a real
    LOINC catalog — Non-Goals). ``status`` is a plain lifecycle string
    (``ordered`` | ``resulted`` | ``cancelled``) driven by the service.
    """

    __tablename__ = "lab_orders"

    encounter_id: Mapped[int] = mapped_column(
        ForeignKey("encounters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordered_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    test_code: Mapped[str] = mapped_column(String(32), nullable=False)
    test_name: Mapped[str] = mapped_column(String(128), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ordered", server_default="ordered"
    )


class LabResult(IdMixin, TimestampMixin, Base):
    """A single measured value recorded against a lab order (append-only).

    A panel can have several analytes, so an order may accumulate multiple result
    rows. ``abnormal`` is the flag computed at record time by the pure lab domain
    rule (against the recorded reference range); ``reference_low``/``high`` capture
    the range used, so the flag is explainable after the fact.
    """

    __tablename__ = "lab_results"

    lab_order_id: Mapped[int] = mapped_column(
        ForeignKey("lab_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recorded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    analyte: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    abnormal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
