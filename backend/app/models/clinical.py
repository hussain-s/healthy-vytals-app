"""Clinical record models — encounters, vitals, diagnoses, and addenda.

These are the heart of the medical record and are governed by the append-only
rule (DESIGN §5.6): once written, an encounter/diagnosis is never edited or
deleted in place; corrections are recorded as :class:`Addendum` rows. The ORM
does not itself forbid updates — immutability is enforced in the service layer —
but the shape here (no "edit" affordances, addenda as separate rows) reflects the
rule, and the KB documents the *why*.

Entities (added across Phase 3 slices):
    * :class:`Encounter` — a clinical visit, opened from an appointment.
    * ``Vitals`` — nurse-recorded measurements (later slice).
    * ``Diagnosis`` — doctor-authored ICD-style finding (later slice).
    * :class:`Addendum` — an immutable correction attached to any clinical record.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Encounter(IdMixin, TimestampMixin, Base):
    """A clinical visit record, opened from a (completed-ish) appointment.

    An encounter is the *record of a visit that happened*, distinct from the
    appointment (the *plan*). It links the patient and the attending doctor and
    is the parent of vitals, diagnoses, and prescriptions for that visit.

    ``opened_at`` is set when the encounter is created; ``closed_at`` is set once
    the doctor finishes documenting. Both are explicit clinical timestamps,
    separate from the row's technical ``created_at``/``updated_at``.

    Append-only (§5.6): the service layer forbids mutating or deleting encounters;
    corrections are Addenda. ``appointment_id`` is unique so at most one encounter
    is opened per appointment.
    """

    __tablename__ = "encounters"

    appointment_id: Mapped[int] = mapped_column(
        ForeignKey("appointments.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Sensitivity + consent gating (§5.8). When an encounter is marked sensitive
    # (e.g. mental-health notes), it is excluded from history views UNLESS the
    # patient has granted consent to share it. The patient viewing their OWN
    # record always sees it; the gate applies to otherwise-authorized staff.
    sensitive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    consent_shared: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )

    __table_args__ = (
        Index("ix_encounters_patient", "patient_id"),
        Index("ix_encounters_doctor", "doctor_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return (
            f"<Encounter id={self.id} patient={self.patient_id} "
            f"doctor={self.doctor_id} closed={self.closed_at is not None}>"
        )


class Vitals(IdMixin, TimestampMixin, Base):
    """A set of vitals recorded by a nurse during an encounter (story C1).

    Values are nullable because a nurse may record only some measurements.
    ``flags`` stores the comma-separated out-of-range markers computed by the
    age-based rule (§5.5, ``domain/vitals_ranges``) at record time — a snapshot of
    what was abnormal *then*, kept append-only with the reading.
    """

    __tablename__ = "vitals"

    encounter_id: Mapped[int] = mapped_column(
        ForeignKey("encounters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recorded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    heart_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resp_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    systolic_bp: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    spo2: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Comma-separated flags (e.g. "heart_rate_high,spo2_low"); empty when normal.
    # server_default uses text("''") so it matches how SQLite reflects the default,
    # preventing a spurious "changed default" diff on every future autogenerate.
    flags: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", server_default=text("''")
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<Vitals id={self.id} encounter={self.encounter_id} flags={self.flags!r}>"


class Diagnosis(IdMixin, TimestampMixin, Base):
    """A doctor-authored diagnosis on an encounter (story C2); append-only (§5.6).

    Carries an ICD-style code and free-text description. Never edited in place —
    corrections are Addenda referencing this row.
    """

    __tablename__ = "diagnoses"

    encounter_id: Mapped[int] = mapped_column(
        ForeignKey("encounters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    icd_code: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<Diagnosis id={self.id} encounter={self.encounter_id} icd={self.icd_code}>"


class Addendum(IdMixin, TimestampMixin, Base):
    """An immutable correction/annotation attached to a clinical record (§5.6).

    Because clinical records are append-only, a mistake is fixed by adding an
    addendum that references the target record, not by editing it — preserving the
    legal history (analogous to an accounting reversing entry). ``target_type`` +
    ``target_id`` form a lightweight polymorphic reference (e.g.
    ``("diagnosis", 42)``) so one addendum table serves every clinical entity.
    """

    __tablename__ = "addenda"

    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[int] = mapped_column(nullable=False)
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    note: Mapped[str] = mapped_column(String(2000), nullable=False)

    __table_args__ = (
        Index("ix_addenda_target", "target_type", "target_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<Addendum id={self.id} target={self.target_type}:{self.target_id}>"
