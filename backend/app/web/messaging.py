"""Web (HTML/HTMX) messaging & notifications: inbox, threads, notification feed.

Thin presentation over messaging_service / notification_service (DESIGN §7.6,
rule 7). Care-team scoping and participant checks live in the services; these
routes render what the caller is allowed to see and post new messages / mark
notifications read via HTMX.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.core.roles import Role
from app.db.session import get_session
from app.models.user import User
from app.repositories.messaging_repository import MessageRepository
from app.repositories.user_repository import UserRepository
from app.services import messaging_service, notification_service
from app.web.deps import require_web_user
from app.web.templates import templates

router = APIRouter(include_in_schema=False)


def _contacts(session: Session, user: User) -> list[User]:
    """People the user can start a conversation with.

    A patient can message clinical staff; a staff member can message patients.
    The service still enforces the fine care-team rule on send — this is only the
    pick-list for the compose form.
    """
    users = UserRepository(session)
    if user.role is Role.PATIENT:
        return users.list_by_role(Role.DOCTOR) + users.list_by_role(Role.NURSE)
    if user.role in (Role.DOCTOR, Role.NURSE):
        return users.list_by_role(Role.PATIENT)
    return []


@router.get("/messages", response_class=HTMLResponse, name="web-messages")
def inbox(
    request: Request,
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """The user's message inbox: every thread they participate in."""
    return templates.TemplateResponse(
        request,
        "messages/inbox.html",
        {
            "user": user,
            "threads": messaging_service.list_threads(session, user.id),
            "contacts": _contacts(session, user),
        },
    )


@router.get("/messages/{thread_id}", response_class=HTMLResponse, name="web-thread")
def thread(
    request: Request,
    thread_id: int,
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """A single conversation: the message history + a reply box."""
    data = messaging_service.get_thread(session, user.id, thread_id)
    return templates.TemplateResponse(
        request,
        "messages/thread.html",
        {"user": user, **data},
    )


@router.post("/messages/{thread_id}/reply", response_class=HTMLResponse,
             name="web-thread-reply")
def reply(
    request: Request,
    thread_id: int,
    body: str = Form(...),
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """HTMX: post a reply in an existing thread; swap back the message list."""
    data = messaging_service.get_thread(session, user.id, thread_id)
    thread = data["thread"]
    counterparty = data["counterparty"]
    error = None
    try:
        messaging_service.send_message(session, user.id, user.role, counterparty.id, body)
    except AppError as exc:
        error = exc.message
        status_code = exc.http_status
    else:
        status_code = 200
    return templates.TemplateResponse(
        request,
        "messages/partials/message_list.html",
        {
            "user": user,
            "messages": MessageRepository(session).list_for_thread(thread_id),
            "error": error,
        },
        status_code=status_code,
    )


@router.post("/messages/compose", response_class=HTMLResponse, name="web-compose-message")
def compose(
    request: Request,
    counterparty_id: int = Form(...),
    body: str = Form(...),
    subject: str = Form(""),
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """HTMX: start (or continue) a conversation from the inbox; swap back the list."""
    error = None
    try:
        messaging_service.send_message(
            session, user.id, user.role, counterparty_id, body, subject=subject or None
        )
    except AppError as exc:
        error = exc.message
        status_code = exc.http_status
    else:
        status_code = 200
    return templates.TemplateResponse(
        request,
        "messages/partials/thread_list.html",
        {
            "user": user,
            "threads": messaging_service.list_threads(session, user.id),
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/notifications", response_class=HTMLResponse, name="web-notifications")
def notifications(
    request: Request,
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """The user's notification feed."""
    return templates.TemplateResponse(
        request,
        "notifications/feed.html",
        {
            "user": user,
            "notifications": notification_service.list_for_user(session, user.id),
        },
    )


@router.post("/notifications/{notification_id}/read", response_class=HTMLResponse,
             name="web-notification-read")
def read_notification(
    request: Request,
    notification_id: int,
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """HTMX: mark one notification read; swap back the refreshed feed."""
    notification_service.mark_read(session, user.id, notification_id)
    return templates.TemplateResponse(
        request,
        "notifications/partials/feed_list.html",
        {"user": user, "notifications": notification_service.list_for_user(session, user.id)},
    )


@router.post("/notifications/read-all", response_class=HTMLResponse,
             name="web-notifications-read-all")
def read_all_notifications(
    request: Request,
    user: User = Depends(require_web_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """HTMX: mark every notification read; swap back the refreshed feed."""
    notification_service.mark_all_read(session, user.id)
    return templates.TemplateResponse(
        request,
        "notifications/partials/feed_list.html",
        {"user": user, "notifications": notification_service.list_for_user(session, user.id)},
    )
