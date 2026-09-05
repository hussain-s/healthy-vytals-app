# ADR-0001 — Local-first: no Docker, SQLite by default

- **Status:** Accepted
- **Date:** 2026-08-08
- **Related:** DESIGN §1, §8, §12.2; [runbooks/setup.md](../runbooks/setup.md)

## Context
The project must be runnable by a college grad on Windows or macOS with minimal
friction, while remaining a realistic, product-shaped app. Docker Desktop is a
common source of setup pain on Windows, and a separate database server is another
install + moving part.

## Decision
- **No Docker.** The whole app runs as a single Uvicorn process on `:8000`.
- **SQLite by default**, as a local file (`backend/healthyvytals.db`), created and
  migrated by the setup scripts. **Python 3.11+ is the only prerequisite.**
- **Postgres is opt-in** via a single `HV_DATABASE_URL` env var, with no code
  changes (SQLAlchemy selects the driver from the URL). The repository layer
  confines all queries so the backend stays swappable.
- One command per OS: `scripts/setup.{sh,ps1}` then `scripts/dev.{sh,ps1}`.

## Consequences
**Positive:** trivial onboarding; the app works offline; no container/daemon; a
newcomer sees a working, seeded app in minutes.
**Negative / mitigations:** SQLite differs from Postgres in some behaviors
(concurrency, types). We mitigate by (a) confining SQL to repositories, (b) using
Alembic batch mode for SQLite-safe migrations, (c) coercing tz-aware datetimes at
the DAL boundary (SQLite drops tzinfo), and (d) keeping the Postgres path a
documented, one-env-var switch so it can be exercised when needed.

## Alternatives considered
- **Docker Compose + Postgres:** most "production-like", but the exact friction we
  set out to remove. Rejected for v1.
- **Postgres installed natively:** still an extra install + service to manage.
  Rejected as the default; retained as opt-in.
