"""Tests for shared API schema primitives (app.schemas.common)."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas.common import ErrorResponse, ORMModel, Page


class _Item(BaseModel):
    name: str


def test_page_carries_items_and_pagination_metadata() -> None:
    page = Page[_Item].create(items=[_Item(name="a")], total=5, limit=1, offset=0)
    assert page.total == 5
    assert page.limit == 1
    assert page.offset == 0
    assert [i.name for i in page.items] == ["a"]


def test_page_rejects_negative_pagination() -> None:
    with pytest.raises(ValidationError):
        Page[_Item](items=[], total=-1, limit=10, offset=0)
    with pytest.raises(ValidationError):
        Page[_Item](items=[], total=0, limit=0, offset=0)  # limit must be >= 1


def test_error_response_defaults_details_to_none() -> None:
    err = ErrorResponse(code="not_found", message="Missing")
    assert err.code == "not_found"
    assert err.details is None


def test_orm_model_populates_from_attributes() -> None:
    """ORMModel maps an object's attributes onto an explicit response schema."""

    class _UserOut(ORMModel):
        email: str

    class _FakeORM:
        email = "a@b.com"
        password_hash = "secret-should-not-leak"

    out = _UserOut.model_validate(_FakeORM())
    assert out.email == "a@b.com"
    # Only declared fields are present — password_hash is not exposed.
    assert "password_hash" not in out.model_dump()
