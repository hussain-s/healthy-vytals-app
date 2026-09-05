"""Messaging service — patient ↔ care-team threads, scoped, audited, notifying (M9).

Orchestrates the M9 use cases (DESIGN §13) inside the caller's unit of work:

    * a patient or staff member **sends** a message to the other party, which
      finds-or-creates the (patient, staff) thread, appends the note, notifies the
      recipient (§M9), and audits;
    * either participant **lists** their threads and **reads** a thread's messages,
      scoped so only the two participants may view it.

Who may participate reuses the care-team scoping (``domain/messaging_rules``),
which itself mirrors the treating-relationship rule used for history and labs
(§5.3). Every action is audited (§5.7). Messages are append-only (§5.6).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import NotFound, PermissionDenied, ValidationError
from app.core.roles import Role
from app.domain.messaging_rules import can_staff_message_patient
from app.models.messaging import Message, MessageThread
from app.repositories.encounter_repository import EncounterRepository
from app.repositories.messaging_repository import (
    MessageRepository,
    MessageThreadRepository,
)
from app.repositories.user_repository import UserRepository
from app.services import notification_service
from app.services.audit_service import record_audit


def _resolve_participants(
    session: Session,
    sender_id: int,
    sender_role: Role,
    counterparty_id: int,
) -> tuple[int, int]:
    """Return ``(patient_id, staff_id)`` for a thread, enforcing care-team scope.

    Exactly one side of a thread is the patient and the other is clinical staff.
    Given a sender and the counterparty, work out which is which, confirm the
    counterparty exists and has the complementary role, and check the care-team
    rule (treating relationship for doctors). Raises on any violation.
    """
    counterparty = UserRepository(session).get(counterparty_id)
    if counterparty is None or not counterparty.is_active:
        raise NotFound(f"No such user: {counterparty_id}")

    if sender_role is Role.PATIENT:
        patient_id, patient_role = sender_id, sender_role
        staff_id, staff_role = counterparty_id, counterparty.role
    else:
        patient_id, patient_role = counterparty_id, counterparty.role
        staff_id, staff_role = sender_id, sender_role

    if patient_role is not Role.PATIENT:
        raise ValidationError("A message thread must have exactly one patient")
    if staff_role not in (Role.NURSE, Role.DOCTOR):
        raise PermissionDenied("Messages are exchanged with clinical staff only")

    treating = (
        EncounterRepository(session).has_treating_relationship(staff_id, patient_id)
        if staff_role is Role.DOCTOR
        else False
    )
    if not can_staff_message_patient(staff_role, treating):
        raise PermissionDenied("You are not on this patient's care team")

    return patient_id, staff_id


def send_message(
    session: Session,
    sender_id: int,
    sender_role: Role,
    counterparty_id: int,
    body: str,
    *,
    subject: str | None = None,
) -> Message:
    """Send a message to the counterparty, creating the thread on first contact.

    Steps (atomic in the caller's unit of work):
      1. Resolve/validate the (patient, staff) pair and care-team scope.
      2. Find-or-create the single thread for that pair.
      3. Append the message (append-only, §5.6).
      4. Notify the recipient (in-app feed, M9) and audit ``message.send``.
    """
    body = (body or "").strip()
    if not body:
        raise ValidationError("Message body must not be empty")

    patient_id, staff_id = _resolve_participants(
        session, sender_id, sender_role, counterparty_id
    )

    threads = MessageThreadRepository(session)
    thread = threads.get_for_pair(patient_id, staff_id)
    if thread is None:
        thread = threads.add(
            MessageThread(patient_id=patient_id, staff_id=staff_id, subject=subject)
        )

    message = MessageRepository(session).add(
        Message(thread_id=thread.id, sender_id=sender_id, body=body)
    )
    # Touch the thread so it sorts to the top of both inboxes.
    thread.updated_at = message.updated_at
    session.flush()

    recipient_id = staff_id if sender_id == patient_id else patient_id
    notification_service.notify(
        session,
        user_id=recipient_id,
        event_type="message.received",
        message="You have a new message.",
        link=f"/messages/{thread.id}",
    )
    record_audit(
        session,
        action="message.send",
        actor_id=sender_id,
        resource_type="message",
        resource_id=message.id,
        patient_id=patient_id,
    )
    return message


def list_threads(session: Session, user_id: int) -> list[dict]:
    """Return the user's threads with their counterparty and last message (inbox)."""
    threads = MessageThreadRepository(session).list_for_user(user_id)
    messages = MessageRepository(session)
    users = UserRepository(session)
    rows: list[dict] = []
    for thread in threads:
        other_id = thread.staff_id if thread.patient_id == user_id else thread.patient_id
        other = users.get(other_id)
        thread_messages = messages.list_for_thread(thread.id)
        rows.append(
            {
                "thread": thread,
                "counterparty": other,
                "last_message": thread_messages[-1] if thread_messages else None,
                "message_count": len(thread_messages),
            }
        )
    return rows


def get_thread(session: Session, user_id: int, thread_id: int) -> dict:
    """Return a thread and its messages if the user is a participant (else 403/404).

    Only the thread's two participants may read it. A non-participant is denied
    (audited ``message.read_denied``, committed so it survives the raise), exactly
    as the lab/history reads treat an unauthorized viewer.
    """
    thread = MessageThreadRepository(session).get(thread_id)
    if thread is None:
        raise NotFound(f"No such thread: {thread_id}")
    if user_id not in (thread.patient_id, thread.staff_id):
        record_audit(
            session,
            action="message.read_denied",
            actor_id=user_id,
            resource_type="message_thread",
            resource_id=thread_id,
            patient_id=thread.patient_id,
            commit=True,
        )
        raise PermissionDenied("You are not a participant in this conversation")

    record_audit(
        session,
        action="message.read",
        actor_id=user_id,
        resource_type="message_thread",
        resource_id=thread_id,
        patient_id=thread.patient_id,
    )
    other_id = thread.staff_id if thread.patient_id == user_id else thread.patient_id
    return {
        "thread": thread,
        "counterparty": UserRepository(session).get(other_id),
        "messages": MessageRepository(session).list_for_thread(thread_id),
    }
