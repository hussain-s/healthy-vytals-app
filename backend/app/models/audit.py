"""Audit log model — the immutable record of who did what, when (§5.7).

Every security- or PHI-relevant action writes one ``AuditLog`` row: an actor, a
verb, the resource touched, and (when known) the patient whose data was involved.
This is the backbone of the HIPAA-style accountability requirement — the app must
be able to answer "who accessed this patient's record and when?".

Design notes:
    * Audit rows are **append-only**: the service layer only ever inserts them,
      never updates or deletes. This mirrors the immutability of clinical records
      (§5.6) and is what makes the log trustworthy.
    * ``actor_id`` is nullable so we can still record actions where no
      authenticated user exists yet — most importantly a **failed login**, which
      is exactly the kind of event an audit trail must capture.
    * ``patient_id`` is nullable because not every audited action concerns a
      patient (e.g. an admin listing users). When set, it is what lets the log be
      filtered "by patient" (story E2).
    * Foreign keys use ``ondelete="SET NULL"`` rather than CASCADE: deleting a
      user must never erase the audit history of what they did.
    * Indexes on ``actor_id``, ``patient_id``, and ``created_at`` support the
      admin's audit queries (filter by user, by patient, by date — story E2).
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class AuditLog(IdMixin, TimestampMixin, Base):
    """An append-only record of a single audited action."""

    __tablename__ = "audit_logs"

    # Who performed the action. Nullable: failed logins have no authenticated user.
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # The action verb, e.g. "user.register", "auth.login", "auth.login_failed".
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    # The kind of resource acted on, e.g. "user", "appointment", "encounter".
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # The specific resource id (as text so it works for any id shape).
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # The patient whose PHI was involved, when applicable (enables "by patient").
    patient_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_audit_logs_actor_id", "actor_id"),
        Index("ix_audit_logs_patient_id", "patient_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return (
            f"<AuditLog id={self.id} action={self.action!r} "
            f"actor={self.actor_id} patient={self.patient_id}>"
        )
