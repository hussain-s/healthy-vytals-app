"""Data-access layer (DAL/DAO) — the only layer that queries the database.

Services and domain never build queries or touch a ``Session`` directly; they go
through a repository (DESIGN §7.6, rule 2). Confining persistence here keeps the
backend swappable (SQLite ↔ Postgres), makes data access independently testable,
and gives scoping/audit a single choke point. ``base.py`` provides a generic
``Repository[ModelT]`` that concrete repositories extend.
"""
