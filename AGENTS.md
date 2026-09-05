# AGENTS.md — how to work in HealthyVytals

Conventions, layering rules, and gotchas for anyone (AI or human) changing this
codebase. Read alongside [docs/knowledge-base/KNOWLEDGE-INDEX.md](docs/knowledge-base/KNOWLEDGE-INDEX.md).

## Golden rules (do not violate)
1. **Respect the layers** (ADR-0004, DESIGN §7.6):
   `web/api → services → domain → repositories → models/db`. Dependencies point
   inward; never skip or reverse.
   - No business logic in routers — they parse/validate, authorize via deps, call
     one service, shape the response.
   - **No DB access outside `repositories/`.**
   - **`domain/` is pure** — no `fastapi`/`sqlalchemy` imports. A guard test
     (`tests/domain/test_domain_purity.py`) fails the build if you break this.
2. **Never serialize ORM objects to clients** — map to explicit `schemas/` models
   (prevents PHI leakage).
3. **Clinical records are append-only** (ADR-0002) — no update/delete of
   encounters/vitals/diagnoses; corrections are `Addendum` rows.
4. **Audit every PHI/security action** via `services/audit_service.record_audit`
   (use `commit=True` on failure paths that then raise).
5. **Errors are typed** — raise `core/exceptions` types; they map to HTTP centrally.

## Working rhythm (DESIGN §9A)
- **One functionality = one commit**, journaled to the deferred-commit ledger
  (`docs/commits/ledger.json` + `docs/COMMIT_LEDGER.md`) — append-only, one entry
  per slice, with the exact file list + a Conventional-Commits message.
- **Definition of Done:** imports/starts, new + full test suite green, KB updated
  in lockstep, self-review, ledger entry written, TASKS.md flipped.
- After editing docs under `docs/`, mirror them:
  `cp -r docs/. ~/shared/webapp/healthyvytals/docs/`.

## Commands
```bash
# tests (run from backend/)
cd backend && ../.venv/bin/python -m pytest -q
# run the app
scripts/dev.sh            # http://localhost:8000
# migrations
scripts/migrate.sh        # alembic upgrade head
```
Note: the shell's working directory can reset between commands — always `cd` to
`backend/` (or use absolute paths) before running pytest/alembic.

## Migration procedure (never blind-commit autogen)
1. Upgrade a scratch DB to head, then
   `alembic revision --autogenerate -m "..."`.
2. **Review** the generated file; flip the `please adjust` marker once verified.
3. Verify upgrade **and** downgrade against a temp SQLite DB.
4. Import the new model module in `alembic/env.py::_import_all_models`.

## Gotchas (these will bite you)
- **SQLite drops tzinfo** → datetimes read back naive. Coerce to UTC-aware at the
  DAL boundary before comparing (see `appointment_repository._as_utc`).
- **String/bool `server_default` false-diffs:** match SQLite's reflected form
  (e.g. `server_default=text("''")`) or autogenerate keeps "detecting" a change.
- **bcrypt pin:** `bcrypt~=4.0.1` (passlib 1.7.4 reads `bcrypt.__about__`, removed
  in 4.1). Don't bump without checking passlib.
- **Request-validation handler** runs `exc.errors()` through `jsonable_encoder`
  (a validator's `ctx` can hold a non-serializable `ValueError`).
- **Auth: two transports, one identity** — API uses `Authorization: Bearer`; the
  web UI uses the HttpOnly `hv_access` cookie. Both resolve via `get_current_user`.
- **Coarse vs fine authorization:** `require_roles` is the role gate; ownership /
  treating-relationship checks live in services (`can_view_patient_history`).
