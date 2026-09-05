"""SQLAlchemy engine and session management (the unit-of-work boundary).

Responsibilities confined to this module (DESIGN §7.2, rule §7.6.2):
    * build the process-wide :class:`~sqlalchemy.engine.Engine` from settings;
    * provide a configured ``sessionmaker``;
    * expose a transactional context manager (:func:`unit_of_work`) and a
      FastAPI-friendly generator (:func:`get_session`) that yields a session and
      guarantees commit-on-success / rollback-on-error / close.

Higher layers ask for a session; they never create engines or manage the
connection pool. This keeps the database backend swappable (SQLite ↔ Postgres)
from a single place, driven entirely by ``HV_DATABASE_URL``.

SQLite note: ``check_same_thread=False`` is required because Uvicorn serves
requests from a threadpool and a session may be used on a different thread than
the one that created the connection. This is safe here because a session is
never shared *concurrently* across threads — each request gets its own.
"""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings


def _engine_kwargs(settings: Settings) -> dict[str, object]:
    """Engine keyword args tailored to the configured backend.

    SQLite needs ``check_same_thread=False`` to be usable from Uvicorn's
    threadpool; other backends (Postgres) use driver defaults.
    """
    if settings.is_sqlite:
        return {"connect_args": {"check_same_thread": False}}
    return {}


@lru_cache
def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy engine (created once, then cached).

    ``future=True`` opts into SQLAlchemy 2.0 semantics. ``pool_pre_ping`` avoids
    handing out connections that a server (e.g. Postgres) has silently dropped.
    """
    settings = get_settings()
    return create_engine(
        settings.database_url,
        future=True,
        pool_pre_ping=True,
        **_engine_kwargs(settings),
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    """Return the process-wide session factory bound to :func:`get_engine`.

    ``expire_on_commit=False`` keeps ORM instances usable after commit, so a
    service can commit and still return populated objects to the API/web layer
    for serialization without triggering a surprise reload.
    """
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        future=True,
    )


@contextmanager
def unit_of_work() -> Iterator[Session]:
    """Provide a transactional scope around a series of operations.

    Commits if the block succeeds, rolls back on any exception, and always closes
    the session. This is the canonical way services wrap a use case so that a
    multi-step operation is atomic (e.g. book a slot *and* create the
    appointment, or neither).
    """
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a transactional session per request.

    Mirrors :func:`unit_of_work` but shaped as a generator so it can be used with
    FastAPI's ``Depends``. The request handler (via services) shares one session;
    it is committed if the request handler returns normally and rolled back if it
    raises, then always closed.
    """
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
