"""HealthyVytals backend application package.

A local-first medical portal built as a modular monolith. See ``docs/DESIGN.md``
for the architecture; the short version is a strict inward-pointing layering:

    web / api  ->  services  ->  domain  ->  repositories  ->  models / db

Sub-packages:
    core          cross-cutting concerns (config, security, roles, deps, errors, audit)
    api           HTTP JSON layer (thin controllers, versioned under /api/v1)
    web           server-rendered Jinja2 + HTMX presentation layer
    schemas       Pydantic request/response models (the serialization boundary)
    services      use-case orchestration + transactions
    domain        pure business rules (no framework/DB imports)
    repositories  the only layer that queries the database
    models        SQLAlchemy ORM entities
    db            engine, session/unit-of-work, seed data
"""
