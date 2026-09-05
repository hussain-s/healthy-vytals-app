"""Data-access for message threads and messages (v2 M9).

Confines messaging queries to the DAL (DESIGN §7.6, rule 2). Services call these;
they never build queries themselves.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.messaging import Message, MessageThread
from app.repositories.base import Repository


class MessageThreadRepository(Repository[MessageThread]):
    def __init__(self, session: Session) -> None:
        super().__init__(MessageThread, session)

    def get_for_pair(self, patient_id: int, staff_id: int) -> MessageThread | None:
        """Return the single thread between this patient and staff member, if any."""
        return self.session.scalar(
            select(MessageThread).where(
                MessageThread.patient_id == patient_id,
                MessageThread.staff_id == staff_id,
            )
        )

    def list_for_user(self, user_id: int) -> list[MessageThread]:
        """Return every thread the user participates in (as patient or as staff).

        Newest-updated first, so the most recently active conversations surface at
        the top of the user's inbox.
        """
        stmt = (
            select(MessageThread)
            .where(
                or_(
                    MessageThread.patient_id == user_id,
                    MessageThread.staff_id == user_id,
                )
            )
            .order_by(MessageThread.updated_at.desc(), MessageThread.id.desc())
        )
        return list(self.session.scalars(stmt).all())


class MessageRepository(Repository[Message]):
    def __init__(self, session: Session) -> None:
        super().__init__(Message, session)

    def list_for_thread(self, thread_id: int) -> list[Message]:
        """Return a thread's messages oldest-first (natural reading order)."""
        stmt = (
            select(Message)
            .where(Message.thread_id == thread_id)
            .order_by(Message.id)
        )
        return list(self.session.scalars(stmt).all())
