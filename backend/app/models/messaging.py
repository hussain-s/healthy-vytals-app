"""Messaging models (v2 M9) — patient ↔ care-team threads and messages.

Models the M9 messaging workflow (DESIGN §13): a patient and a clinical-staff
member (their care team) exchange messages inside a shared :class:`MessageThread`;
each note is a :class:`Message` row. There is at most one thread per
(patient, staff) pair, so a conversation is continuous rather than fragmented.

Append-only, consistent with the rest of the record (§5.6, ADR-0002): messages
are never edited or deleted in place. Who may participate is a care-team scoping
decision (treating relationship for doctors) enforced in the service, mirroring
the history/lab visibility rules (§5.3); the models themselves only capture the
two participants and the notes exchanged.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class MessageThread(IdMixin, TimestampMixin, Base):
    """A conversation between one patient and one clinical-staff member.

    A thread is keyed by its two participants: ``patient_id`` and ``staff_id``.
    The unique pair constraint guarantees a single continuous thread per
    (patient, staff) relationship — starting a "new" conversation with someone
    you already message reuses the existing thread (see the service).
    """

    __tablename__ = "message_threads"

    patient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    staff_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)

    __table_args__ = (
        UniqueConstraint("patient_id", "staff_id", name="uq_message_thread_pair"),
    )


class Message(IdMixin, TimestampMixin, Base):
    """A single note in a thread, authored by one of its two participants.

    Append-only (§5.6): messages are inserted, never mutated. ``sender_id`` is one
    of the thread's participants (enforced in the service); the recipient is the
    other participant, who is notified when the message is sent.
    """

    __tablename__ = "messages"

    thread_id: Mapped[int] = mapped_column(
        ForeignKey("message_threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    body: Mapped[str] = mapped_column(String(4000), nullable=False)
