"""SQLAlchemy ORM entities — the persistence models.

This is the only layer that defines database tables. Repositories query these
models; services and domain never import them directly for querying (they go
through repositories). Keeping every table definition here gives Alembic a single
place to autogenerate migrations from.
"""
