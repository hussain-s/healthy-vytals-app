"""Notification service — the single choke point for raising in-app alerts (M9).

Every in-app notification is created through :func:`notify`, mirroring the way
:mod:`app.services.audit_service` centralizes the audit trail. Domain use cases
(a message sent, an appointment booked, a lab resulted) call :func:`notify` to
emit an alert for the affected user; the notification is written **inside the
caller's unit of work**, so an event and its notification commit or roll back
together.

``event_type`` uses the dotted ``resource.verb`` convention (``message.received``,
``appointment.booked``, ``lab.resulted``, ``prescription.created``) so the feed is
greppable and consistent with the audit vocabulary.

Reads and mark-read live here too: the feed for a user, its unread count, and
marking notifications read. Authorization (a user only ever touches their own
notifications) is enforced by these functions scoping every query to ``user_id``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.repositories.notification_repository import NotificationRepository


def notify(
    session: Session,
    *,
    user_id: int,
    event_type: str,
    message: str,
    link: str | None = None,
) -> Notification:
    """Create one in-app notification for ``user_id`` within the caller's transaction.

    Keyword-only (except the session) so call sites are self-documenting. Flushes
    but does not commit — atomic with the originating event. Returns the row so
    callers/tests can assert on it.
    """
    return NotificationRepository(session).add(
        Notification(
            user_id=user_id,
            event_type=event_type,
            message=message,
            link=link,
        )
    )


def list_for_user(
    session: Session, user_id: int, *, limit: int = 50
) -> list[Notification]:
    """Return a user's notification feed, newest first."""
    return NotificationRepository(session).list_for_user(user_id, limit=limit)


def unread_count(session: Session, user_id: int) -> int:
    """Return the number of unread notifications for a user (the nav badge count)."""
    return NotificationRepository(session).unread_count(user_id)


def mark_read(session: Session, user_id: int, notification_id: int) -> bool:
    """Mark one of the user's notifications read; return whether it was found.

    Scoped to ``user_id`` so a user can never mark someone else's notification
    read. Idempotent: marking an already-read notification leaves its timestamp
    unchanged. Returns ``False`` (not an error) if the id does not belong to the
    user, so the caller can decide how to respond.
    """
    repo = NotificationRepository(session)
    notification = repo.get(notification_id)
    if notification is None or notification.user_id != user_id:
        return False
    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        session.flush()
    return True


def mark_all_read(session: Session, user_id: int) -> int:
    """Mark all of a user's unread notifications read; return how many changed."""
    repo = NotificationRepository(session)
    now = datetime.now(timezone.utc)
    changed = 0
    for notification in repo.list_for_user(user_id, limit=1000):
        if notification.read_at is None:
            notification.read_at = now
            changed += 1
    if changed:
        session.flush()
    return changed
