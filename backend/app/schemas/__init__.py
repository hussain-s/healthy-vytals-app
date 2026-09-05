"""Pydantic v2 request/response models — the API serialization boundary.

Schemas are deliberately distinct from ORM models (``app.models``). We never
serialize ORM objects directly to clients; a route maps them to an explicit
response schema so field exposure is intentional and PHI cannot leak by accident
(DESIGN §7.6, rule 4). ``common.py`` holds the shared envelope types (pagination,
error shape) so every endpoint is consistent.
"""
