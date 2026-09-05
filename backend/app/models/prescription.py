"""Prescription domain models — medications, allergies, interactions, prescriptions.

These back the prescription-safety rule (§5.4): before a drug is prescribed the
service checks the patient's recorded allergies (hard block), known drug-drug
interactions with active medications (warn + override), and controlled-substance
refill caps. The models here hold the *facts* those checks consult; the pure
decision logic lives in ``domain/prescription_safety.py``.

Entities:
    * :class:`Medication` — the curated drug catalog (name, class, controlled).
    * :class:`Allergy` — a patient's recorded allergy (by substance/med class).
    * :class:`DrugInteraction` — a curated interacting pair + severity.
    * :class:`Prescription` — a doctor's order tied to an encounter, safety-checked.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Medication(IdMixin, TimestampMixin, Base):
    """A drug in the curated catalog.

    ``drug_class`` groups related drugs (an allergy to a class blocks all members).
    ``is_controlled`` marks controlled substances, which cap refills (§5.4).
    """

    __tablename__ = "medications"

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    drug_class: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    is_controlled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )


class Allergy(IdMixin, TimestampMixin, Base):
    """A patient's recorded allergy.

    An allergy may be recorded against a specific medication (``medication_id``)
    or a whole drug class (``substance`` holding the class/substance name), so the
    safety check can hard-block either an exact drug or its class (§5.4).
    """

    __tablename__ = "allergies"

    patient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    substance: Mapped[str] = mapped_column(String(128), nullable=False)
    reaction: Mapped[str | None] = mapped_column(String(255), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)


class DrugInteraction(IdMixin, TimestampMixin, Base):
    """A curated interacting pair of medications, with severity.

    Stored once per unordered pair (the service normalizes lookups). Severity is
    an advisory string (e.g. "moderate", "severe") shown in the warning.
    """

    __tablename__ = "drug_interactions"

    medication_a_id: Mapped[int] = mapped_column(
        ForeignKey("medications.id", ondelete="CASCADE"), nullable=False
    )
    medication_b_id: Mapped[int] = mapped_column(
        ForeignKey("medications.id", ondelete="CASCADE"), nullable=False
    )
    severity: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint("medication_a_id", "medication_b_id", name="uq_interaction_pair"),
        Index("ix_drug_interactions_a", "medication_a_id"),
        Index("ix_drug_interactions_b", "medication_b_id"),
    )


class Prescription(IdMixin, TimestampMixin, Base):
    """A doctor's medication order tied to an encounter (safety-checked on create)."""

    __tablename__ = "prescriptions"

    encounter_id: Mapped[int] = mapped_column(
        ForeignKey("encounters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prescriber_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    medication_id: Mapped[int] = mapped_column(
        ForeignKey("medications.id", ondelete="RESTRICT"), nullable=False
    )
    dose: Mapped[str] = mapped_column(String(128), nullable=False)
    refills: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
