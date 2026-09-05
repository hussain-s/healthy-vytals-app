"""HTTP JSON API layer — thin controllers only.

Routers here parse/validate input (Pydantic), authorize via dependencies, call a
single service method, and shape the response. They contain no business logic and
no direct database access (DESIGN §7.6, rule 1). The API is versioned from day
one: all routes mount under ``/api/v1`` (see ``router.py`` and ``v1/``).
"""
