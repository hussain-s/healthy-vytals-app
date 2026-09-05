# HealthyVytals — Conversation Log & AI Handoff

> **Purpose of this file.** It is a self-contained handoff so **any** AI (or human) can read
> it and immediately understand what this project is, every decision made so far, the current
> state of the repo, the working rules, and exactly where to resume — without needing the
> original chat transcript.
>
> **Read order for a new AI:** (1) this file → (2) `docs/DESIGN.md` → (3) `docs/TASKS.md` →
> (4) `docs/commits/README.md` + `docs/COMMIT_LEDGER.md`. Then continue from §8 "Where we
> left off" below.
>
> **Last updated:** 2026-08-08.

---

## 1. What we are building

**HealthyVytals** — a local-first, full-stack **medical portal** where **patients, nurses,
doctors, and an admin** register, book appointments, run the clinical workflow (triage →
vitals → consult → diagnose → prescribe), and view role-scoped medical history.

Future product domain: **HealthyVytals.ai**.

### The real goal (why this project exists)
The app is a vehicle to prove a hypothesis:

> An AI given a **curated knowledge base** over a codebase can understand the system
> end-to-end and make correct changes, whereas an AI given only the raw source (as on a
> public GitHub repo) produces shallow or wrong answers.

So the domain is deliberately chosen to be **rule-heavy and non-obvious** (clinical access
control, appointment state machines, prescription safety, append-only records). The code is
paired with an authored knowledge base (ADRs, glossary, business rules, ERD, workflows,
runbooks) kept in lockstep with the code.

---

## 2. How we got here (chronology of the conversation)

1. **Original ask:** author a reusable "principal engineer" prompt to build an end-to-end
   app (frontend + backend + database) runnable locally by a college grad, and propose a few
   app options. The codebase should be knowledge-base-rich to prove the hypothesis above.
2. First response produced the prompt + three options (LedgerLite / StockRoom / DeskFlow) on a
   React + NestJS + Postgres/Docker stack; recommended LedgerLite. Saved a brief at
   `~/shared/webapp/PROJECT-BRIEF.md` (now stale — see §7).
3. **Pivot:** user changed direction — build a **Medical Portal**, switch backend to
   **Python/FastAPI**, and **drop Docker** (Windows users struggle with Docker Desktop).
4. Entered plan-first mode. An engineering **design document** was authored.
5. **Naming:** iterated on the product name; landed on **HealthyVytals** (domain
   HealthyVytals.ai). Folder + docs updated accordingly.
6. **Methodology added:** implement **one functionality at a time = one commit**, to protect
   AI context (avoid context-window exhaustion + lossy summarization) and keep progress
   recoverable. Held to a **high, principal-engineer-review-grade** quality bar.
7. **Clean slate:** because the design iterated a lot after some early code was written, the
   user asked to **delete all implementation** and reset those tasks to Not Started. Done —
   only design docs remain; no implementation exists.
8. **Standards guideline:** enforce a well-defined **monolith folder structure** with proper
   abstractions, API models/shapes, and layered separation — **no shortcuts**. Codified into
   DESIGN §7.5–§7.6.
9. **Deferred commits:** git is not initialized here, so we maintain a **commit ledger**
   (metadata) that another AI can later replay into a clean git history. Built and documented.
10. **This file:** created so the whole context is portable and reusable.
11. **§12 decisions CONFIRMED (2026-08-08):** frontend = **Jinja2 + HTMX (no Node)**; SQLite
    default; Admin included; scope = Epics A–E; Alembic + one-command wrapper. Docs updated
    to make the web layer server-rendered (`backend/app/web/`), single process on `:8000`.

---

## 3. Locked decisions

- **Domain:** Medical portal (HealthyVytals).
- **Backend:** Python 3.11+ / FastAPI, Pydantic v2, SQLAlchemy 2.0.
- **Frontend:** **Jinja2 + HTMX, server-rendered by FastAPI** — no React, no Node, no build
  step. The whole app is **one process on `:8000`**. Presentation layer lives at
  `backend/app/web/`. Browser session via **HttpOnly cookie**; JSON API also accepts Bearer.
- **Database:** **SQLite** file by default (no server, no Docker); Postgres is an opt-in via a
  single `DATABASE_URL` env var.
- **Migrations:** **Alembic**, behind one-command wrapper scripts (`scripts/migrate.*`,
  `scripts/reset-db.*`).
- **No Docker.** Runs natively on **Windows and macOS**; **Python 3.11+ is the only
  prerequisite** (no Node). One-command-per-OS scripts (`scripts/setup.*`, `scripts/dev.*`).
- **Roles:** Patient, Nurse, Doctor, **Admin** (admin exists for user mgmt + audit-log access;
  it has **no** clinical authoring rights — least privilege).
- **Single monolith repository** containing backend, frontend, docs, scripts.
- **Layered architecture** with strict boundaries (see §4).
- **Process:** one functionality → one commit; commits journaled to a ledger until git exists.
- **Quality bar:** written to survive aggressive principal-engineer review; no shortcuts.
- **Code location:** `~/.workspace/healthyvytals/`. Review docs mirrored to
  `~/shared/webapp/healthyvytals/docs/`.

---

## 4. Architecture (summary — full detail in DESIGN §7)

Single-direction request flow; dependencies point inward, never skip or reverse:

```
HTTP → api/v1/*  → services/*  → domain/*  → repositories/*  → models/ + db/
        (thin        (use-case     (pure        (ONLY layer      (ORM +
        controllers) orchestration) rules,      that queries     session)
                                    no I/O)      the DB)
```

Key non-negotiable rules:
- No business logic in routers. No raw DB access outside `repositories/`.
- `domain/` is pure (no FastAPI/SQLAlchemy imports) → unit-testable rules.
- **API models (`schemas/`) are separate from ORM models (`models/`)** — never serialize ORM
  objects directly (prevents PHI leakage).
- API **versioned from day one** (`/api/v1`); standardized `Page[T]`, `ErrorResponse`, and
  typed domain errors mapped to stable HTTP codes.

Folder contract lives in **DESIGN §7.5**; layering rules in **DESIGN §7.6**.

---

## 5. Domain & business rules (the "knowledge-base gold")

Full detail in DESIGN §4–§6. The non-obvious rules an AI cannot guess from code:

1. **Appointment state machine** — legal transitions only; role-gated (DESIGN §5.1).
2. **Slot conflict & buffer** — no double-booking; buffer between appts; cancellation cutoff (§5.2).
3. **Treating-relationship scoping** — a doctor sees full history only for patients they treat (§5.3).
4. **Prescription safety** — hard-block on allergy match; warn on drug interaction; refill caps
   on controlled substances (§5.4).
5. **Vitals normal ranges** vary by age → out-of-range flags the encounter (§5.5).
6. **Immutable clinical records** — encounters/diagnoses/prescriptions are append-only;
   corrections are **addenda**, never in-place edits (§5.6).
7. **Mandatory audit logging** on every PHI read/write (§5.7).
8. **Consent gating** on sensitive categories (§5.8).

Access-control matrix (role × action) is in DESIGN §6.

---

## 6. Working rules for any AI continuing this project

1. **One functionality = one commit.** Small vertical slices (model + schema + domain rule +
   service + route + tests + doc update). Never batch.
2. **Definition of Done before "commit"** (DESIGN §9A.2): imports/starts cleanly, new tests +
   full suite green, knowledge base updated in lockstep, self-review passed, message written.
3. **Journal every commit to the ledger** (DESIGN §9A.6): write source files AND append one
   ordered, append-only entry to `docs/commits/ledger.json` + mirror in
   `docs/COMMIT_LEDGER.md`, in the same step. Never edit past entries — changes = new entry.
4. **Update `docs/TASKS.md`** status in the same step (flip ⬜→✅ truthfully).
5. **Hold the high bar** (DESIGN §9A.4): correctness + edge cases, security (least-privilege,
   no auth bypass, validated input, no string-built SQL), clarity, consistency, real tests.
6. **Keep docs in both locations in sync:** edit under `~/.workspace/healthyvytals/`, then copy
   the docs to `~/shared/webapp/healthyvytals/docs/`.
7. **Be honest about status.** If something is partial or a shortcut was taken, say so.

---

## 7. Current repo state (files that actually exist)

**Phase 0 is COMPLETE** (2026-08-08) — 11 ledger slices (c001–c011). The app boots as a
single Uvicorn process on `:8000` serving the web UI + JSON API + `/docs`. A Python venv
lives at `.venv/` (git-ignored). Full test suite: **50 passed**.

```
~/.workspace/healthyvytals/
├── README.md · Makefile · .gitignore · .env.example
├── scripts/            # setup / dev / migrate / seed / reset-db  (.sh + .ps1)
├── backend/
│   ├── requirements.txt · pyproject.toml · alembic.ini
│   ├── alembic/         # env.py (settings-driven) + versions/ (empty until Phase 1)
│   ├── app/
│   │   ├── main.py      # app factory: mounts /api, /static, web router, error handlers
│   │   ├── core/        # config.py, roles.py, security.py, errors.py
│   │   ├── api/{router.py, v1/health.py}
│   │   ├── schemas/common.py   # ORMModel, Page[T], ErrorResponse
│   │   ├── repositories/base.py# generic Repository[Model]
│   │   ├── models/base.py      # Base + Id/Timestamp mixins
│   │   ├── db/{session.py, seed.py}
│   │   └── web/         # templates.py, router.py, templates/*, static/{app.css, htmx.min.js}
│   └── tests/           # core/, db/, api/, schemas/, repositories/, web/  (50 tests)
└── docs/                # DESIGN.md, TASKS.md, CONVERSATION-LOG.md, COMMIT_LEDGER.md, commits/
```

Still empty (created with their first code in Phase 1+): `app/services/`, `app/domain/`.

Note: UI is server-rendered (`backend/app/web/`, Jinja2+HTMX) — there is **no** separate
`frontend/` project and no Node toolchain.

Mirrored copy of `docs/` is at `~/shared/webapp/healthyvytals/docs/`.

**Stale artifact:** `~/shared/webapp/PROJECT-BRIEF.md` is the ORIGINAL finance/inventory brief
from before the pivot. It does not describe HealthyVytals. Scheduled to be rewritten in
Phase 6 (TASKS 6.5).

---

## 8. Where we left off — resume here

**Status:** 🎉 **ALL SIX PHASES COMPLETE** — 58 ledger slices (c001–c058), **262 tests passing**.
All five §12 decisions CONFIRMED. Migration chain head = `f8d94a046c95` (9 migrations). The
project exit gate is met: a fresh clone → one command per OS → migrate + seed → a working,
seeded app on `:8000` where all four demo roles log in and see the seeded clinical journey.
Phase 6 delivered a rich clinical-journey seed, a §5-rule→test traceability matrix, a web
route-test sweep, a finalized README, a rewritten PROJECT-BRIEF, and end-to-end verification —
which caught and fixed a real bug (demo emails used the reserved `.local` TLD that Pydantic
`EmailStr` rejects; switched to `@healthyvytals.example.com`).

**The build is functionally complete.** Remaining work is external to this environment: initialize
git and **replay the deferred-commit ledger** (`docs/commits/ledger.json`, 58 entries) into a clean
history — see `docs/commits/README.md`. Demo accounts (password `Passw0rd!`):
`patient@ / nurse@ / doctor@ / admin@healthyvytals.example.com`.

Phase 1 (Accounts & RBAC): User + 1:1 profiles + AuditLog; auth service (register/login/refresh)
+ `core/security`/`core/deps`; auth + admin-provisioning endpoints; append-only audit; 4-role
seed; KB (ADR-0003, access-matrix, glossary).

Phase 2 (Availability & appointments): `AvailabilitySlot` + `Appointment` models (5 migrations,
chain head = `7c55e96cd3c2`); **pure `domain/` layer** — `appointment_state.py` (state machine
§5.1, role-gated) and `scheduling_rules.py` (conflict/buffer + late-cancel §5.2), guarded by a
domain-purity test; `appointment_service` (publish/book/change_status) + repositories; JSON
endpoints (slots, booking, transitions, doctor/nurse schedule views); **web UI** — cookie-session
login/register/logout (`web/auth.py`, `web/deps.py`), per-role dashboards, and an HTMX patient
booking flow; concurrency race test (unique `slot_id`); KB (business-rules #1/#2 + two workflow
diagrams). Also extracted `core/exceptions.py` (framework-free) so the domain stays pure.
Three real bugs were found by tests and fixed: failure-audit rollback loss, a request-validation
handler serialization crash (needs `jsonable_encoder`), and naive/aware datetime comparison
(SQLite drops tzinfo — coerce to UTC at the DAL boundary).

Phase 3 (Clinical workflow & history): `models/clinical.py` (Encounter, Vitals, Diagnosis,
Addendum — append-only; 3 migrations, chain head = `69a027b6d00b`); pure domain rules
`vitals_ranges.py` (§5.5 age-banded flags), `access_scope.py` (§5.3 treating-relationship +
§5.8 consent gate); `clinical_service` (open encounter, record vitals w/ flagging, diagnose,
addenda, treating-scoped + consent-filtered history, all audited); `encounter_repository`;
JSON endpoints (`/encounters` + vitals/diagnoses/addenda/history); web clinical screens
(patient history, doctor encounter page w/ HTMX diagnosis add). Append-only enforced by
exposing only create/addendum ops (no update/delete route). **218 tests passing.**

Phase 4 (Prescriptions & safety): `models/prescription.py` (Medication, Allergy,
DrugInteraction, Prescription); pure `domain/prescription_safety.py` (§5.4 — allergy hard-block
non-overridable, interaction warn+override, controlled refill cap); `prescription_service` +
`prescription_repository` (allergy terms + interacting active meds); `/api/v1/prescriptions`
(prescribe safety-checked + reads); web prescribe form on the encounter page + patient rx list;
seed extended with 5 meds + 2 interactions; KB rule #4 + prescribe workflow. Also rooted out the
recurring `vitals.flags` autogenerate false-diff via `server_default=text("''")`.

**Next up:** nothing within this environment — all planned phases are done. The natural
follow-ups are the git replay (above) and any new features the user chooses to scope, which
would continue as further ledger slices under the same §9A methodology.

**Working reminders for the continuing AI:** each slice = write code + tests, run the full
suite green, append ONE append-only entry to `docs/commits/ledger.json` (schema is strict —
`seq/id/message{subject,body}/files/task_ids/rule_refs/phase/rationale/depends_on`, no extra
keys), mirror it in `COMMIT_LEDGER.md`, flip the TASKS.md row, then `cp -r docs/.
~/shared/webapp/healthyvytals/docs/`. Run pytest from `backend/` via `../.venv/bin/python -m
pytest`. Clean any runtime `backend/healthyvytals.db` after manual boots (it's git-ignored).

**Historical note (superseded):** the lines below were written before implementation began.

**Confirmed §12 decisions:**

| # | Decision | Confirmed choice |
|---|---|---|
| 12.1 | Frontend | **Jinja2 + HTMX**, server-rendered by FastAPI (no Node/React/build) |
| 12.2 | Database | **SQLite** default (Postgres opt-in via `DATABASE_URL`) |
| 12.3 | Admin role | **Included** (user mgmt + audit log; no clinical authoring) |
| 12.4 | v1 scope | **Epics A–E** as written in DESIGN §3 |
| 12.5 | Migrations | **Alembic** with one-command wrapper scripts |

**Immediate next actions — first Phase 0 slices, each its own ledger entry** (see TASKS §2,
rows 0.1–0.18):
1. Repo layout + `.gitignore` + `.env.example` + `backend/requirements.txt` + `pyproject.toml`.
2. `backend/app/core/config.py` (env-driven Settings, SQLite default).
3. DB engine/session + declarative `Base` (+ id/timestamp mixins).
4. Alembic init + `scripts/migrate.*` one-command wrapper.
5. FastAPI app factory + `/health` + versioned `/api/v1` router mount.
6. Common API primitives (`schemas/common.py`: `Page[T]`, `ErrorResponse`; `core/errors.py`).
7. Generic repository base (`repositories/base.py`).
8. `web/` bootstrap: `Jinja2Templates` + `base.html` + vendored HTMX + a rendered landing page.
9. Setup/dev scripts for Windows + macOS (single Uvicorn process); README quick-start.
→ Phase 0 exit: `scripts/dev.*` boots the single-process app on `:8000` (web UI + `/docs`).

Then proceed to Phase 1 (Accounts & RBAC) and onward per TASKS.md.

**Note:** the user has not yet given the explicit go-ahead to begin writing implementation
code. Confirm before starting slice 1, or proceed if already authorized.

---

## 9. Pointers (all paths relative to `~/.workspace/healthyvytals/`)

- **Spec / decisions:** `docs/DESIGN.md` (esp. §7.5–§7.6 layout & rules, §9A methodology,
  §12 open decisions).
- **Progress:** `docs/TASKS.md`.
- **Commit history (deferred):** `docs/COMMIT_LEDGER.md`, `docs/commits/ledger.json`,
  `docs/commits/README.md`.
- **This handoff:** `docs/CONVERSATION-LOG.md`.
