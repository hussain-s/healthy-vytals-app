"""Database engine, session factory, unit-of-work, and seed data.

This package owns the SQLAlchemy ``Engine`` and ``Session`` lifecycle. Everything
above it (repositories) receives a ``Session`` to work with and never constructs
engines or sessions itself. Confining that here keeps the persistence backend
(SQLite by default, Postgres opt-in) swappable from one place.
"""
