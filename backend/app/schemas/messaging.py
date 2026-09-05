"""Messaging & notification API schemas (v2 M9)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class MessageCreate(BaseModel):
    counterparty_id: int
    body: str = Field(min_length=1, max_length=4000)
    subject: str | None = Field(default=None, max_length=200)


class MessageOut(ORMModel):
    id: int
    thread_id: int
    sender_id: int
    body: str
    created_at: datetime


class ThreadOut(ORMModel):
    id: int
    patient_id: int
    staff_id: int
    subject: str | None


class ThreadDetailOut(BaseModel):
    thread: ThreadOut
    counterparty_id: int
    messages: list[MessageOut]


class NotificationOut(ORMModel):
    id: int
    event_type: str
    message: str
    link: str | None
    read_at: datetime | None
    created_at: datetime


class NotificationReadOut(BaseModel):
    """Result of a mark-read action: what changed + the caller's new unread count.

    Returning the fresh ``unread_count`` lets a client update its nav badge from
    the same response, without a follow-up request.
    """

    updated: int = Field(description="How many notifications this action marked read.")
    unread_count: int = Field(description="The caller's remaining unread count.")
