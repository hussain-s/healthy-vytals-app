"""Data-access for in-app notifications (v2 M9).

Confines notification queries to the DAL (DESIGN §7.6, rule 2). Services call
these; they never build queries themselves.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.repositories.base import Repository


class NotificationRepository(Repository[Notification]):
    def __init__(self, session: Session) -> None:
        super().__init__(Notification, session)

    def list_for_user(self, user_id: int, *, limit: int = 50) -> list[Notification]:
        """Return a user's notifications, newest first."""
        stmt = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.id.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def unread_count(self, user_id: int) -> int:
        """Return how many of the user's notifications are still unread."""
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
        return self.session.scalar(stmt) or 0
