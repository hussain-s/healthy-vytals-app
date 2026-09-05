# Runbook — setup, seed, reset, troubleshooting

Operational how-to for running HealthyVytals locally. Prerequisite: **Python
3.11+** only (no Node, no Docker). See also the top-level [README](../../../README.md).

## First-time setup
```bash
# macOS/Linux
scripts/setup.sh      # venv + deps + migrate + seed
scripts/dev.sh        # serve on http://localhost:8000

# Windows (PowerShell)
./scripts/setup.ps1
./scripts/dev.ps1
```
Then open `http://localhost:8000/` (UI) and `/docs` (API). Demo accounts (all
password `Passw0rd!`): `patient@ / nurse@ / doctor@ / admin@healthyvytals.example.com`.

## Common tasks
| Task | Command (macOS/Linux) | Notes |
|---|---|---|
| Apply migrations | `scripts/migrate.sh` | `alembic upgrade head` |
| Load demo data | `scripts/seed.sh` | idempotent; 4 users, 5 meds, 2 interactions |
| Reset the DB | `scripts/reset-db.sh` | drops SQLite file, re-migrates, re-seeds (SQLite only) |
| Run tests | `cd backend && ../.venv/bin/python -m pytest` | full suite |
| Use Postgres | set `HV_DATABASE_URL=postgresql+psycopg://…` | no code change; then migrate |

## Seed data
`app/db/seed.py` is idempotent (upsert by natural key), so re-running is safe. It
seeds one user per role, a small medication catalog (incl. a controlled
substance), and interacting pairs (Warfarin+Aspirin severe, Warfarin+Ibuprofen
moderate) so the prescribe-safety flow is demoable.

## Migrations
- Autogenerate: upgrade a scratch DB to head first, then
  `alembic revision --autogenerate -m "..."`, **review** the output (never commit
  blindly — DESIGN §8), flip the "please adjust" marker, verify up + downgrade.
- SQLite uses **batch mode** (render_as_batch) so column changes work.

## Troubleshooting / known gotchas
- **`virtual environment not found`** — run the setup script first.
- **Port 8000 busy** — `PORT=9000 scripts/dev.sh` (or `$env:PORT=9000` on Windows).
- **PowerShell blocks scripts** — `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- **Naive vs aware datetimes** — SQLite drops tzinfo; the DAL coerces stored
  datetimes back to UTC-aware. Keep new datetime comparisons on the aware side.
- **Autogenerate shows a `vitals.flags` default diff** — should not recur;
  `server_default=text("''")` matches SQLite's reflected form. If a similar false
  diff appears for a new string/bool default, match the reflected representation.
- **bcrypt/passlib** — pinned `bcrypt~=4.0.1` (passlib 1.7.4 reads
  `bcrypt.__about__`, removed in 4.1). Don't bump bcrypt without checking passlib.

## Failure modes worth knowing
- A failed login / denied history read / blocked prescription still writes an
  audit row (committed independently) — check `audit_logs` when investigating.
- Clinical records are append-only: there is no edit/delete; corrections are
  addenda (ADR-0002).
