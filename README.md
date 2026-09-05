# HealthyVytals

A local-first, full-stack **medical portal** where patients, nurses, doctors, and
a clinic admin register, book appointments, run the clinical workflow (triage →
vitals → consult → diagnose → prescribe), and view role-scoped medical history.

HealthyVytals is built as a **knowledge-base-rich reference application**: the
domain is deliberately rule-heavy (clinical access control, appointment state
machines, prescription safety, append-only records) and every non-obvious rule is
documented alongside the code in [`docs/`](docs/). See
[`docs/DESIGN.md`](docs/DESIGN.md) for the full engineering design.

> Educational reference app — **not** HIPAA-certified or production-secure.

---

## Prerequisites

**Python 3.11 or newer — and nothing else.** No Node.js, no Docker, no database
server. The UI is server-rendered (Jinja2 + HTMX) and the database is a local
SQLite file, so the whole app runs as **one process on port 8000**.

- macOS: `brew install python@3.12` (or python.org installer)
- Windows: install from [python.org](https://www.python.org/downloads/) and tick
  **"Add python.exe to PATH"**

Check your version:

```bash
python3 --version    # macOS/Linux
python --version     # Windows
```

---

## Quick start (one command per OS)

**macOS / Linux**

```bash
scripts/setup.sh     # create venv, install deps, migrate, seed
scripts/dev.sh       # start the app on http://localhost:8000
```

**Windows (PowerShell)**

```powershell
./scripts/setup.ps1  # create venv, install deps, migrate, seed
./scripts/dev.ps1    # start the app on http://localhost:8000
```

Then open:

- **Web UI:** <http://localhost:8000/>
- **Interactive API docs (OpenAPI):** <http://localhost:8000/docs>
- **Health check:** <http://localhost:8000/api/v1/health>

> If PowerShell blocks the scripts with an execution-policy error, allow local
> scripts for the current user once:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### Demo accounts (seeded)

Setup seeds one account per role plus a complete demo clinical journey (a
completed appointment with vitals, a diagnosis, and a prescription). Log in with
any of these — **password `Passw0rd!`**:

| Role | Email | Can do |
|---|---|---|
| Patient | `patient@healthyvytals.example.com` | Book appointments, view own history + prescriptions |
| Nurse | `nurse@healthyvytals.example.com` | Ward schedule, check-in, record vitals |
| Doctor | `doctor@healthyvytals.example.com` | Availability, consult, diagnose, prescribe |
| Admin | `admin@healthyvytals.example.com` | Provision staff accounts, read the audit log |

### What you can do (v1 features)

- **Accounts & RBAC** — patient self-registration; admin-provisioned staff; JWT
  (API) or HttpOnly-cookie (web) sessions; role-gated actions.
- **Appointments** — doctors publish availability; patients book open slots;
  a state machine drives confirm → check-in → in-progress → complete, with
  cancel/no-show; double-booking and buffer conflicts are blocked; late
  cancellations are flagged.
- **Clinical workflow** — nurse records vitals (out-of-range values flagged by
  age); doctor opens an encounter and records diagnoses; records are append-only
  (corrections are addenda); history is scoped to the treating relationship;
  sensitive encounters are consent-gated.
- **Prescriptions** — safety-checked: allergy matches are hard-blocked, drug
  interactions warn (overridable), controlled substances cap refills.
- **Audit** — every PHI/security action is logged (admins can review).

The *why* behind these rules lives in
[`docs/knowledge-base/`](docs/knowledge-base/KNOWLEDGE-INDEX.md).

---

## Common tasks

| Task | macOS/Linux | Windows | `make` |
|---|---|---|---|
| First-time setup | `scripts/setup.sh` | `./scripts/setup.ps1` | `make setup` |
| Run the app | `scripts/dev.sh` | `./scripts/dev.ps1` | `make dev` |
| Apply migrations | `scripts/migrate.sh` | `./scripts/migrate.ps1` | `make migrate` |
| Load demo data | `scripts/seed.sh` | `./scripts/seed.ps1` | `make seed` |
| Reset the database | `scripts/reset-db.sh` | `./scripts/reset-db.ps1` | `make reset-db` |
| Run the tests | `cd backend && ../.venv/bin/python -m pytest` | `cd backend; ..\.venv\Scripts\python -m pytest` | `make test` |

`make` (macOS/Linux) mirrors the shell scripts; run `make help` to list targets.

---

## Configuration

All settings are environment-driven with safe local defaults, so the app runs
with **no `.env` file**. To override, copy the template and edit it:

```bash
cp .env.example .env
```

Key variables (see [`.env.example`](.env.example) for the full list):

- `HV_DATABASE_URL` — defaults to a local SQLite file. Point it at
  `postgresql+psycopg://…` to use Postgres instead — **no code changes needed**.
- `HV_JWT_SECRET_KEY` — signing key for auth tokens; override for any shared use.

---

## Project layout

```
healthyvytals/
├── backend/
│   ├── app/
│   │   ├── core/          # config, security, roles, errors (cross-cutting)
│   │   ├── api/v1/         # JSON API (thin controllers, versioned)
│   │   ├── web/            # server-rendered Jinja2 + HTMX UI
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── services/       # use-case orchestration (Phase 1+)
│   │   ├── domain/         # pure business rules (Phase 1+)
│   │   ├── repositories/   # data-access layer (the only layer touching the DB)
│   │   ├── models/         # SQLAlchemy ORM entities
│   │   └── db/             # engine/session, seed data
│   ├── alembic/            # database migrations
│   └── tests/              # mirrors app/ (domain, services, api, web)
├── scripts/               # setup / dev / migrate / seed / reset-db (.sh + .ps1)
└── docs/                  # DESIGN.md, TASKS.md, knowledge base
```

The architecture and layering rules are documented in
[`docs/DESIGN.md`](docs/DESIGN.md) §7. Progress is tracked in
[`docs/TASKS.md`](docs/TASKS.md).

---

## Troubleshooting

- **`virtual environment not found`** — run the setup script for your OS first.
- **Port 8000 in use** — run on another port: `PORT=9000 scripts/dev.sh` (macOS/
  Linux) or `$env:PORT=9000; ./scripts/dev.ps1` (Windows).
- **PowerShell won't run scripts** — see the execution-policy note above.
- **Start over from a clean database** — run the `reset-db` script for your OS.
