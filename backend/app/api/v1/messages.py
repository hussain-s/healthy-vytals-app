"""Messaging & notification API endpoints (JSON, v2 M9).

Thin controllers over messaging_service / notification_service. Any authenticated
user may use these; the fine care-team scoping (who may message whom, who may read
a thread) lives in the service, and notifications are always scoped to the caller.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_session
from app.models.user import User
from app.schemas.messaging import (
    MessageCreate,
    MessageOut,
    NotificationOut,
    NotificationReadOut,
    ThreadDetailOut,
    ThreadOut,
)
from app.services import messaging_service, notification_service

router = APIRouter(tags=["messaging"])


@router.get("/messages/threads", response_model=list[ThreadOut],
            summary="List the caller's message threads")
def list_threads(
    viewer: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[ThreadOut]:
    rows = messaging_service.list_threads(session, viewer.id)
    return [ThreadOut.model_validate(r["thread"]) for r in rows]


@router.get("/messages/threads/{thread_id}", response_model=ThreadDetailOut,
            summary="Read a thread's messages (participants only)")
def get_thread(
    thread_id: int,
    viewer: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ThreadDetailOut:
    data = messaging_service.get_thread(session, viewer.id, thread_id)
    return ThreadDetailOut(
        thread=ThreadOut.model_validate(data["thread"]),
        counterparty_id=data["counterparty"].id if data["counterparty"] else 0,
        messages=[MessageOut.model_validate(m) for m in data["messages"]],
    )


@router.post("/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED,
             summary="Send a message to a care-team member or patient")
def send_message(
    payload: MessageCreate,
    sender: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> MessageOut:
    message = messaging_service.send_message(
        session, sender.id, sender.role, payload.counterparty_id,
        payload.body, subject=payload.subject,
    )
    return MessageOut.model_validate(message)


@router.get("/notifications", response_model=list[NotificationOut],
            summary="The caller's in-app notifications (newest first)")
def list_notifications(
    viewer: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[NotificationOut]:
    return [
        NotificationOut.model_validate(n)
        for n in notification_service.list_for_user(session, viewer.id)
    ]


@router.post("/notifications/{notification_id}/read", response_model=NotificationReadOut,
             summary="Mark one notification read")
def mark_notification_read(
    notification_id: int,
    viewer: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> NotificationReadOut:
    updated = notification_service.mark_read(session, viewer.id, notification_id)
    return NotificationReadOut(
        updated=int(updated),
        unread_count=notification_service.unread_count(session, viewer.id),
    )


@router.post("/notifications/read-all", response_model=NotificationReadOut,
             summary="Mark all of the caller's notifications read")
def mark_all_notifications_read(
    viewer: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> NotificationReadOut:
    updated = notification_service.mark_all_read(session, viewer.id)
    return NotificationReadOut(
        updated=updated,
        unread_count=notification_service.unread_count(session, viewer.id),
    )
