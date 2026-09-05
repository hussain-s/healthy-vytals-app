"""Shared API schema primitives: pagination envelope and error shape.

Standardizing these here (DESIGN §7.6, rule 5) means every list endpoint returns
the same ``Page[T]`` shape and every error returns the same ``ErrorResponse``,
so clients — and the OpenAPI docs — see one consistent contract across the whole
API.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# --- ORM-friendly response base --------------------------------------------


class ORMModel(BaseModel):
    """Base for response schemas that are populated from ORM instances.

    ``from_attributes=True`` lets a router do ``UserOut.model_validate(user_orm)``
    to map an ORM object onto an explicit response schema — the deliberate step
    that keeps field exposure intentional (rule 4) rather than dumping the ORM row.
    """

    model_config = ConfigDict(from_attributes=True)


# --- Pagination -------------------------------------------------------------

ItemT = TypeVar("ItemT")


class Page(BaseModel, Generic[ItemT]):
    """A single page of results plus the metadata needed to request more.

    Generic over the item type, so an endpoint declares ``Page[UserOut]`` and both
    the response and the OpenAPI schema are precisely typed.
    """

    items: list[ItemT] = Field(description="The results on this page.")
    total: int = Field(description="Total number of matching items across all pages.", ge=0)
    limit: int = Field(description="Maximum number of items requested per page.", ge=1)
    offset: int = Field(description="Number of items skipped before this page.", ge=0)

    @classmethod
    def create(
        cls, items: list[ItemT], total: int, limit: int, offset: int
    ) -> "Page[ItemT]":
        """Convenience constructor mirroring the fields, for readable call sites."""
        return cls(items=items, total=total, limit=limit, offset=offset)


# --- Error shape ------------------------------------------------------------


class ErrorResponse(BaseModel):
    """The single error envelope every failing endpoint returns.

    ``code`` is a stable, machine-readable string (e.g. ``"slot_conflict"``) that
    clients can branch on without parsing prose; ``message`` is human-readable and
    safe to display. ``details`` optionally carries structured, non-sensitive
    context (e.g. which field failed validation).
    """

    code: str = Field(description="Stable, machine-readable error code.")
    message: str = Field(description="Human-readable, client-safe description.")
    details: dict[str, object] | None = Field(
        default=None, description="Optional structured, non-sensitive context."
    )
