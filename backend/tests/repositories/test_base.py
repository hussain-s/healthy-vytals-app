"""Tests for the generic repository base (app.repositories.base).

Exercises get/list/count/add/delete and the flush-on-add contract against a real
in-memory SQLite session, using a throwaway model so the test is independent of
any concrete domain entity.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import String, create_engine, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from app.models.base import Base, IdMixin, TimestampMixin
from app.repositories.base import Repository


class _Gadget(IdMixin, TimestampMixin, Base):
    __tablename__ = "_test_gadget"
    name: Mapped[str] = mapped_column(String(50), nullable=False)


class _GadgetRepository(Repository[_Gadget]):
    def __init__(self, session: Session) -> None:
        super().__init__(_Gadget, session)

    def get_by_name(self, name: str) -> _Gadget | None:
        return self.session.scalar(select(_Gadget).where(_Gadget.name == name))


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", future=True, connect_args={"check_same_thread": False})
    _Gadget.__table__.create(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as s:
        yield s
    engine.dispose()


def test_add_flushes_and_populates_generated_fields(session: Session) -> None:
    repo = _GadgetRepository(session)
    gadget = repo.add(_Gadget(name="alpha"))
    # id + timestamps are available immediately after add(), before any commit.
    assert gadget.id is not None
    assert gadget.created_at is not None


def test_get_returns_entity_or_none(session: Session) -> None:
    repo = _GadgetRepository(session)
    created = repo.add(_Gadget(name="alpha"))
    assert repo.get(created.id) is created
    assert repo.get(999_999) is None


def test_list_is_paginated_and_ordered_by_id(session: Session) -> None:
    repo = _GadgetRepository(session)
    for name in ("a", "b", "c"):
        repo.add(_Gadget(name=name))

    first_two = repo.list(limit=2, offset=0)
    assert [g.name for g in first_two] == ["a", "b"]

    last_one = repo.list(limit=2, offset=2)
    assert [g.name for g in last_one] == ["c"]


def test_count_reflects_row_total(session: Session) -> None:
    repo = _GadgetRepository(session)
    assert repo.count() == 0
    repo.add(_Gadget(name="a"))
    repo.add(_Gadget(name="b"))
    assert repo.count() == 2


def test_delete_removes_entity(session: Session) -> None:
    repo = _GadgetRepository(session)
    gadget = repo.add(_Gadget(name="doomed"))
    repo.delete(gadget)
    assert repo.count() == 0


def test_subclass_query_method_works(session: Session) -> None:
    repo = _GadgetRepository(session)
    repo.add(_Gadget(name="findme"))
    found = repo.get_by_name("findme")
    assert found is not None
    assert found.name == "findme"
