"""Generic repository base — the shared CRUD foundation for the DAL.

``Repository[ModelT]`` provides the handful of persistence operations nearly
every entity needs (get, list with pagination, add, delete, count) against a
single SQLAlchemy model, using a ``Session`` supplied by the caller. Concrete
repositories subclass it and add entity-specific queries (e.g. "find open slots
for a doctor between two times"), keeping *all* query construction inside this
layer (DESIGN §7.6, rule 2).

Design choices:
    * **The session is injected, never created here.** The unit-of-work boundary
      (commit/rollback) lives in ``db.session`` / the service layer; a repository
      only reads and stages writes. This keeps a single transaction spanning
      multiple repositories within one use case.
    * **``add`` flushes but does not commit.** Flushing populates
      server-generated fields (primary key, timestamps) so the caller can use
      them immediately, while leaving the commit decision to the unit of work.
    * **Generic over the model type** so subclasses get typed returns without
      re-implementing boilerplate.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class Repository(Generic[ModelT]):
    """Generic CRUD repository for a single ORM model.

    Subclass with a concrete model, e.g.::

        class UserRepository(Repository[User]):
            def __init__(self, session: Session) -> None:
                super().__init__(User, session)

            def get_by_email(self, email: str) -> User | None:
                return self.session.scalar(select(User).where(User.email == email))
    """

    def __init__(self, model: type[ModelT], session: Session) -> None:
        self.model = model
        self.session = session

    def get(self, entity_id: int) -> ModelT | None:
        """Return the entity with ``entity_id`` or ``None`` if it does not exist."""
        return self.session.get(self.model, entity_id)

    def list(self, *, limit: int = 50, offset: int = 0) -> list[ModelT]:
        """Return a page of entities ordered by primary key.

        Ordering by ``id`` gives a stable, deterministic page sequence (important
        for predictable pagination); callers needing domain-specific ordering add
        a method on their concrete repository.
        """
        stmt = select(self.model).order_by(self.model.id).limit(limit).offset(offset)
        return list(self.session.scalars(stmt).all())

    def count(self) -> int:
        """Return the total number of rows for this model."""
        return self.session.scalar(select(func.count()).select_from(self.model)) or 0

    def add(self, entity: ModelT) -> ModelT:
        """Stage ``entity`` for insertion and flush to populate generated fields.

        Flushing (not committing) sends the INSERT so the DB assigns the primary
        key and timestamps, making them readable immediately, while the enclosing
        unit of work still owns the commit/rollback decision.
        """
        self.session.add(entity)
        self.session.flush()
        return entity

    def delete(self, entity: ModelT) -> None:
        """Stage ``entity`` for deletion (committed by the unit of work).

        NOTE: append-only clinical records (DESIGN §5.6) must never be deleted;
        that rule is enforced in the service layer. This generic method exists for
        entities where deletion is legitimate (e.g. an unbooked availability slot).
        """
        self.session.delete(entity)
        self.session.flush()
