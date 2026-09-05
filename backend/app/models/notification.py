"""Notification model (v2 M9) — in-app alerts raised by domain events.

A :class:`Notification` is a lightweight, per-user alert emitted when something
the user cares about happens: a new message, an appointment booked/cancelled, a
lab result recorded, a prescription written. It powers the in-app notification
feed in the app shell (DESIGN §13, M9).

Notifications are **not** clinical records: they are a derived read-model, so
unlike encounters/vitals they are mutable in exactly one way — the recipient may
mark one read (``read_at``). They are never edited otherwise. Emission is a
best-effort side effect of the originating use case, written inside the same unit
of work as the event so an event and its notification commit together.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Notification(IdMixin, TimestampMixin, Base):
    """An in-app alert addressed to one user.

    ``event_type`` is a dotted ``resource.verb`` string (e.g. ``message.received``,
    ``appointment.booked``, ``lab.resulted``) mirroring the audit action vocabulary,
    so the feed is greppable and filterable. ``link`` is an optional in-app URL the
    feed row deep-links to. ``read_at`` is null until the recipient marks it read.
    """

    __tablename__ = "notifications"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
