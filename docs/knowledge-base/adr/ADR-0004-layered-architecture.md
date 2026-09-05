# ADR-0004 — Layered architecture with a pure domain

- **Status:** Accepted
- **Date:** 2026-08-08
- **Related:** DESIGN §7.2, §7.5, §7.6

## Context
The value of this project is a rule-heavy domain that an AI can reason about. That
requires the rules to live somewhere explicit, testable, and framework-free —
not scattered through routers and ORM callbacks.

## Decision
Strict inward-pointing layers; dependencies never skip or reverse:

```
web / api  ->  services  ->  domain  ->  repositories  ->  models / db
```

Non-negotiable rules (DESIGN §7.6):
1. **No business logic in routers.** `api/` and `web/` parse/validate, authorize
   via deps, call one service, shape the response.
2. **No DB access outside `repositories/`.** Keeps persistence swappable and
   queries testable/auditable.
3. **`domain/` is pure** — no FastAPI/SQLAlchemy imports; takes values, returns
   decisions. A guard test fails the build if a domain module imports a framework.
4. **Schemas ≠ ORM models** — responses map to explicit Pydantic schemas so PHI
   can't leak by accident.
5. **API versioned from day one** (`/api/v1`), standardized `Page[T]`/`ErrorResponse`.
6. **Typed domain errors** mapped centrally to HTTP.
7. **Web layer is presentation-only**, over the same services as the API.

## Consequences
**Positive:** the hard rules (state machine, scheduling, vitals ranges, scoping,
prescription safety) are unit-tested without a DB or HTTP; the JSON API and the
HTMX UI share one behavior source; backends are swappable. This is what makes the
codebase read like a product, not a prototype.
**Negative / mitigations:** more indirection than a CRUD app needs — deliberate
(DESIGN §7.6 "standard, not shortcut"). The layering is enforced by the purity
test and code review, and documented here + in the glossary so it stays honest.

## Alternatives considered
- **Fat models / active record:** rules on the ORM; fast to write, but couples
  rules to persistence and resists pure testing. Rejected.
- **Logic in routers:** duplicates behavior across the API and web surfaces and
  can't be unit-tested off HTTP. Rejected.
