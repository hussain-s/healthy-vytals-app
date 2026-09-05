# HealthyVytals — Implementation Task Tracker

> **Purpose:** A single, always-current map of *what is built* vs. *what remains*, derived
> from `DESIGN.md`. Any AI or engineer picking up this project should read this file
> **first** (together with `DESIGN.md`) to understand the state of the world before making
> changes.
>
> **How to use this file (rules for AI + humans):**
> - Statuses: ✅ **Done** · 🟡 **In Progress** · ⬜ **Not Started** · 🚫 **Blocked** · ⏭️ **Deferred (out of v1 scope)**
> - When you complete a task, flip its status **in the same commit** as the code, and note the commit/date.
> - One functionality = one commit (see `DESIGN.md` §9A). Do not batch tasks.
> - If you add scope, add a row here — never leave work untracked.
> - "DoD" = Definition of Done from `DESIGN.md` §9A.2 (tests pass, full suite green, KB updated, self-review, commit message).
>
> **Last updated:** 2026-08-08 · **Legend maps to** `DESIGN.md` phases §9 and rules §5.
>
> **Reset note (2026-08-08):** All previously written implementation code was deliberately
> **deleted** and its tasks reset to ⬜ Not Started. The design was iterated substantially
> after that early code was written, so we start implementation from scratch to honor the
> approved design and the one-commit-per-functionality methodology. Only `docs/DESIGN.md`
> and `docs/TASKS.md` (the iterated design) were kept. No implementation exists yet.

---

## 0. Status Summary (at a glance)

| Phase | Title | Progress |
|---|---|---|
| Pre | Design & methodology | ✅ Done |
| 0 | Scaffolding & local run (no Docker) | ✅ Done (11 slices, c001–c011; exit gate met) |
| 1 | Accounts & RBAC | ✅ Done (14 slices c012–c022; exit gate met) |
| 2 | Availability & appointments | ✅ Done (12 slices c023–c034; exit gate met) |
| 3 | Clinical workflow & medical history | ✅ Done (9 slices c035–c043; exit gate met) |
| 4 | Prescriptions & safety | ✅ Done (7 slices c044–c050; exit gate met) |
| 5 | Knowledge base authoring | ✅ Done (authored in lockstep + finalized c051–c053) |
| 6 | Tests, seed data, polish | ✅ Done (5 slices c054–c058; project exit gate met) |
| — | **v2 addendum (DESIGN §13)** | — |
| 7 | Real role dashboards + UI shell | ✅ Done (c060–c065; all roles live) |
| 8 | Lab results & reports (new domain) | ✅ Done (c066–c070; exit gate met) |
| 9 | Messaging & in-app notifications | ✅ Done (c071; exit gate met) |
| 12 | AI vitals assistant + LLM component layer (§14) | ✅ Done (c072–c074; exit gate met) |
| 13 | Vitals trends, booking UX & visual refresh (§15) | ✅ Done (c075–c077; exit gate met) |
| 10 | Documents & vitals trends | ⬜ Not Started |
| 11 | v2 polish, rich seed, e2e verification | ⬜ Not Started |

**Blockers / decisions needed before Phase 0 can complete:**
- ✅ **Open decisions (`DESIGN.md` §12) CONFIRMED (2026-08-08):** frontend = **Jinja2 + HTMX (no Node)**; **SQLite** default (Postgres opt-in); **Admin included**; scope = **Epics A–E**; migrations = **Alembic** + one-command wrapper. No decision blockers remain.

**Commits:** Git is not initialized here. Each functionality is recorded as an entry in the
**deferred-commit ledger** (`docs/COMMIT_LEDGER.md` + `docs/commits/ledger.json`, per
`DESIGN.md` §9A.6) so the exact history can be replayed later. This is **not** a blocker —
work proceeds normally; commits are journaled instead of executed.

---

## 1. Pre-work — Design & Methodology

| # | Task | Status | Artifact / Notes |
|---|---|---|---|
| P.1 | Engineering design document | ✅ Done | `docs/DESIGN.md` |
| P.2 | Execution methodology (1 commit/functionality, quality bar) | ✅ Done | `DESIGN.md` §9A |
| P.3 | Product naming (HealthyVytals) chosen & applied to folder + docs | ✅ Done | `~/.workspace/healthyvytals/`, docs; future domain `HealthyVytals.ai` |
| P.4 | This task tracker | ✅ Done | `docs/TASKS.md` |
| P.5 | Monolith folder contract + layering/abstraction rules | ✅ Done | `DESIGN.md` §7.5–§7.6 |
| P.6 | Deferred-commit ledger mechanism (schema + replay + files) | ✅ Done | `DESIGN.md` §9A.6; `docs/commits/` |

---

## 2. Phase 0 — Scaffolding & Local Run (no Docker)

| # | Task | Status | Artifact / Notes |
|---|---|---|---|
| 0.1 | Repo directory layout (backend/app/{core,api,web,...}, docs, scripts) | 🟡 In Progress | dirs exist; stale `frontend/` removed (§12.1); `web/` pkg added in slice 0.12. Ledger c001 |
| 0.2 | Backend dependency manifest (FastAPI, SQLAlchemy, Alembic, Jinja2, jose, passlib, pytest) | ✅ Done | `backend/requirements.txt` · Ledger c001 |
| 0.3 | App config (env-driven, SQLite default, domain tunables) | ✅ Done | `backend/app/core/config.py` · 4 tests · Ledger c002 |
| 0.4 | Role enum + RBAC groupings | ✅ Done | `backend/app/core/roles.py` · 6 tests · Ledger c003 |
| 0.5 | Security: password hashing + JWT create/decode | ✅ Done | `backend/app/core/security.py` · 10 tests · Ledger c004 (pins bcrypt 4.0.x) |
| 0.6 | DB engine + session/unit-of-work + declarative `Base` (+ id/timestamp mixins) | ✅ Done | `backend/app/db/session.py`, `models/base.py` · 5 tests · Ledger c005 |
| 0.7 | Alembic init + one-command migrate wrapper (`scripts/migrate.*`) | ✅ Done | `alembic/`, `alembic.ini`, `scripts/migrate.{sh,ps1}` (§12.5) · autogenerate smoke-tested · Ledger c010 |
| 0.8 | FastAPI app factory + `/health` + versioned router mount (`/api/v1`) | ✅ Done | `backend/app/main.py`, `api/router.py`, `api/v1/health.py` · 4 tests · Ledger c006 |
| 0.9 | Common API primitives: `Page[T]`, `ErrorResponse`, typed errors + handlers | ✅ Done | `schemas/common.py`, `core/errors.py` · 9 tests · Ledger c007 |
| 0.10 | Generic repository base (`Repository[Model]`) — DAL foundation | ✅ Done | `repositories/base.py` · 6 tests · Ledger c008 |
| 0.11 | Package `__init__.py` across layers (api/web/domain/models/schemas/services/repositories/db) | 🟡 In Progress | done: app, core, models, db, api, api/v1, schemas, repositories, web (+ test pkgs). Remaining: `services/`, `domain/` (added in Phase 1+) |
| 0.12 | Web layer bootstrap: `Jinja2Templates`, `web/router.py`, `base.html`, vendored `htmx.min.js`, `app.css` | ✅ Done | `backend/app/web/` (§7.3) · HTMX 2.0.3 vendored · Ledger c009 |
| 0.13 | Rendered landing page + `/` route (proves server-render + HTMX load) | ✅ Done | `web/templates/`, `web/static/` · 6 tests + live boot check · Ledger c009 |
| 0.14 | Setup scripts — Windows `setup.ps1` / macOS `setup.sh` (venv+deps+migrate+seed) | ✅ Done | `scripts/setup.{sh,ps1}` · Ledger c011 |
| 0.15 | Dev scripts — `dev.ps1` / `dev.sh` (single Uvicorn process, autoreload) | ✅ Done | `scripts/dev.{sh,ps1}` · boot-verified · Ledger c011 |
| 0.16 | `reset-db` + `seed` helper scripts + `Makefile` | ✅ Done | `scripts/{reset-db,seed}.{sh,ps1}`, `Makefile`, `app/db/seed.py` · Ledger c011 |
| 0.17 | `.gitignore` + `.env.example` + `pyproject.toml` (lint/format/test config) | ✅ Done | repo root, `backend/` · Ledger c001 |
| 0.18 | README quick-start (Python-only prereqs, one-command run, troubleshooting) | ✅ Done | `README.md` · Ledger c011 |
| 0.19 | Deferred-commit ledger infra (`COMMIT_LEDGER.md`, `commits/ledger.json`, schema/replay README) | ✅ Done | replaces `git init` until git exists (§9A.6) |
| **Exit** | `dev` script boots API + UI on Windows & macOS | ✅ Done | macOS/Linux verified (dev.sh → /, /api/v1/health, /docs all 200); Windows scripts authored (parity, not run in this Linux env) · Ledger c011 |

---

## 3. Phase 1 — Accounts & RBAC  (User Stories A1–A5)

| # | Task | Status | Rule / Story | Notes |
|---|---|---|---|---|
| 1.1 | `User` model (email, password_hash, role, is_active) | ✅ | A1–A3 | `models/user.py` + first migration · 3 tests · Ledger c012 |
| 1.2 | Profile models: Patient / Doctor / Nurse (1:1 with User) | ✅ | §4.1 | `models/profile.py` + migration · 5 tests · Ledger c013 |
| 1.3 | Pydantic schemas (register, login, token, user-out) | ✅ | A1,A3 | `schemas/auth.py`, `schemas/user.py` · 6 tests · Ledger c014 |
| 1.4 | Auth service: register patient (self-service) | ✅ | A1 | `services/auth_service.py` + `POST /api/v1/auth/register` · 10 tests · Ledger c017 |
| 1.5 | Admin-provisioned staff accounts | ✅ | A2 | `services/auth_service.provision_staff` + `POST /api/v1/users` (admin-only) · 7 tests · Ledger c019 |
| 1.6 | Login endpoint → access + refresh tokens | ✅ | A3 | `api/v1/auth.py` · Ledger c018 |
| 1.7 | Refresh endpoint (reject access-as-refresh & vice versa) | ✅ | A4 | uses `type` claim · Ledger c018 |
| 1.8 | `get_current_user` dependency (decode + load) | ✅ | A3,A5 | `core/deps.py` (Bearer + cookie) · Ledger c018 |
| 1.9 | `require_roles(...)` guard | ✅ | A5 | 403 on mismatch · Ledger c018 |
| 1.10 | `AuditLog` model | ✅ | §5.7 | `models/audit.py` + migration · 2 tests · Ledger c016 |
| 1.11 | Audit write helper + wire into auth paths | ✅ | §5.7 | helper c016; wired into register+login (c017). Extends to each new PHI path per phase |
| 1.12 | Seed representative users (all 4 roles) | ✅ | — | `db/seed.py` (idempotent, demo pw `Passw0rd!`) · 3 tests · Ledger c020 |
| 1.13 | Tests: register/login/refresh, 403 matrix, audit rows | ✅ | A1–A5,§5.7 | `tests/api/test_rbac_integration.py` + per-slice tests (110 total) · Ledger c022 (fixed failure-audit rollback bug) |
| 1.14 | KB update: ADR-0003 auth, access-matrix.md, glossary terms | ✅ | §11 | `knowledge-base/adr/ADR-0003…`, `domain/access-matrix.md`, `domain/glossary.md` · Ledger c021 |
| **Exit** | All 4 roles log in; forbidden actions 403; audit rows appear | ✅ | | exit-gate integration test green · Ledger c022 |

---

## 4. Phase 2 — Availability & Appointments  (User Stories B1–B6)

| # | Task | Status | Rule / Story | Notes |
|---|---|---|---|---|
| 2.1 | `AvailabilitySlot` model | ✅ | B1 | `models/scheduling.py` + migration · 2 tests · Ledger c023 |
| 2.2 | Doctor publishes/reads own slots (endpoints) | ✅ | B1 | `appointment_service.publish_slot` + `POST /slots`, `GET /slots/mine`, `GET /slots/open/{id}` + repos · 9 tests · Ledger c027 |
| 2.3 | `Appointment` model (+ status enum) | ✅ | §4.1 | `models/scheduling.py` (unique slot_id) + migration · 3 tests · Ledger c026 |
| 2.4 | Appointment **state machine** (legal transitions) | ✅ | **§5.1** | pure `domain/appointment_state.py` (+ `core/exceptions.py`) · 9 tests + purity guard · Ledger c024 |
| 2.5 | Booking service: patient books open slot | ✅ | B2 | `book_appointment` + `POST /appointments`, `GET /appointments/mine` · 6 tests · Ledger c028 |
| 2.6 | Conflict + **buffer** enforcement (no overlap/double-book) | ✅ | **§5.2** | `domain/scheduling_rules.py` · 11 tests · Ledger c025 |
| 2.7 | Cancellation w/ **cutoff** flag (late cancel) | ✅ | **§5.2** | B4 · `change_status` frees slot + sets `cancelled_late` · Ledger c029 |
| 2.8 | State-advance endpoints (check-in/begin/complete/no-show) | ✅ | B6,§5.1 | `POST /appointments/{id}/transitions/{transition}` · 11 tests · Ledger c029 |
| 2.9 | Schedule views (ward for nurse, calendar for doctor) | ✅ | B5 | `GET /appointments/doctor`, `GET /appointments/ward` (nurse-only; v1 single-ward) · Ledger c030 |
| 2.10 | Concurrency guard on "last slot" (race safety) | ✅ | §5.2 | unique(slot_id) proven by `test_booking_concurrency.py` · Ledger c030 |
| 2.11 | Web (HTMX): booking flow + role dashboards (templates + partials) | ✅ | B2,B5 | cookie auth + dashboards (c031) + HTMX booking flow (c032) · 13 web tests |
| 2.12 | Tests: legal/illegal transitions, double-book, buffer, late-cancel, race | ✅ | §5.1,§5.2 | domain + service + API + `test_scheduling_integration.py` · Ledger c033 |
| 2.13 | KB update: business-rules #1,#2; workflow diagrams (book, cancel/no-show) | ✅ | §11 | `domain/business-rules.md`, `workflows/appointment-{booking,lifecycle}.md` · Ledger c034 |
| **Exit** | Patient books; staff advances state; double-book/late-cancel blocked | ✅ | | exit-gate integration test green · Ledger c033 |

---

## 5. Phase 3 — Clinical Workflow & Medical History  (User Stories C1–C6)

| # | Task | Status | Rule / Story | Notes |
|---|---|---|---|---|
| 3.1 | `Encounter` model (append-only) | ✅ | §5.6 | `models/clinical.py` (+ Addendum) + migration · 4 tests · Ledger c035 |
| 3.2 | `Vitals` model (+ nurse-entered) | ✅ | C1 | `models/clinical.py` + migration · Ledger c038 |
| 3.3 | **Vitals range check** by patient age → `flags` | ✅ | **§5.5** | `domain/vitals_ranges.py` · 7 tests · Ledger c036 |
| 3.4 | `Diagnosis` model (ICD code + notes, append-only) | ✅ | C2,§5.6 | `models/clinical.py` + migration · Ledger c038 |
| 3.5 | `Addendum` model + create (corrections, never edit) | ✅ | **§5.6** | C3 · model c035, `clinical_service.add_addendum` c039 |
| 3.6 | Immutability enforcement (block edits/deletes on clinical rows) | ✅ | **§5.6** | service exposes create/addendum only (no update/delete) · Ledger c039 |
| 3.7 | **Treating-relationship scoping** predicate | ✅ | **§5.3** | `domain/access_scope.py` · 4 tests · Ledger c037 |
| 3.8 | Patient views own full history | ✅ | C4 | `get_patient_history` + `GET /encounters/history/{id}` · Ledger c039 |
| 3.9 | Doctor views history only for treated patients | ✅ | C5,§5.3 | audited denials (`history.read_denied`) · Ledger c039 |
| 3.10 | Consent gating on sensitive categories (v1 flag) | ✅ | §5.8 | `is_encounter_visible` + Encounter flags + history filter · 6 tests · Ledger c040 |
| 3.11 | Audit wiring for all PHI reads/writes here | ✅ | §5.7 | encounter/vitals/diagnosis/addendum/history all audited · Ledger c039 |
| 3.12 | Web (HTMX): encounter/vitals/history pages (role-aware templates + partials) | ✅ | C1–C5 | `web/clinical.py` + `web/templates/encounters/` · 4 tests · Ledger c041 |
| 3.13 | Tests: ranges/flags, append-only, addendum, scoping allow/deny, consent | ✅ | §5.3,§5.5,§5.6,§5.8 | domain+service+API + `test_clinical_integration.py` · Ledger c042 |
| 3.14 | KB update: business-rules #3,#5,#6,#8; ERD; triage→consult workflow | ✅ | §11 | `business-rules.md` #3/#5/#6/#8 + `workflows/triage-to-consult.md` · Ledger c043 (ERD deferred to Phase 5) |
| **Exit** | Nurse→doctor flow works; scoping + append-only enforced | ✅ | | exit-gate integration test green · Ledger c042 |

---

## 6. Phase 4 — Prescriptions & Safety  (User Stories D1–D5)

| # | Task | Status | Rule / Story | Notes |
|---|---|---|---|---|
| 4.1 | `Medication` catalog model (+ `is_controlled`, drug_class) | ✅ | §4.1 | `models/prescription.py` + migration · Ledger c044 |
| 4.2 | `Allergy` model (patient allergies) | ✅ | D2 | `models/prescription.py` · Ledger c044 |
| 4.3 | `DrugInteraction` model (curated pairs + severity) | ✅ | D3 | `models/prescription.py` · Ledger c044 |
| 4.4 | `Prescription` model (+ status, refills) | ✅ | D1 | `models/prescription.py` · 5 tests · Ledger c044 |
| 4.5 | **Allergy hard-block** check | ✅ | **§5.4** | `domain/prescription_safety.py` · 9 tests · Ledger c045 |
| 4.6 | **Drug-interaction warn** (override flag required) | ✅ | **§5.4** | D3 · `evaluate_prescription` override · Ledger c045 |
| 4.7 | **Controlled-substance refill cap** | ✅ | **§5.4** | D4 · Ledger c045 |
| 4.8 | Prescribe endpoint (doctor only, safety-checked) | ✅ | D1,§5.4 | `prescription_service.prescribe` + `POST /prescriptions` · 10 tests · Ledger c046 |
| 4.9 | Patient views active/past prescriptions | ✅ | D5 | `GET /prescriptions/mine` + `/patient/{id}` · Ledger c046 |
| 4.10 | Seed medications/allergies/interactions | ✅ | — | `db/seed.py` (5 meds + 2 interactions) · 2 tests + live · Ledger c047 |
| 4.11 | Web (HTMX): prescribe form + prescriptions list (with safety warnings) | ✅ | D1,D5 | `web/clinical.py` + `web/templates/prescriptions/` · 3 tests · Ledger c048 |
| 4.12 | Tests: allergy block, interaction warn/override, refill cap, happy path | ✅ | §5.4 | domain+service+API + `test_prescription_integration.py` · Ledger c049 |
| 4.13 | KB update: business-rules #4; prescribe workflow diagram | ✅ | §11 | `business-rules.md` #4 + `workflows/prescribe.md` · Ledger c050 |
| **Exit** | Unsafe prescription blocked with clear error; safe one succeeds | ✅ | | exit-gate integration test green · Ledger c049 |

---

## 7. Phase 5 — Knowledge Base Authoring  (finalize; kept in lockstep)

| # | Task | Status | Artifact |
|---|---|---|---|
| 5.1 | `KNOWLEDGE-INDEX.md` (map an AI reads first) | ✅ | `docs/knowledge-base/KNOWLEDGE-INDEX.md` · Ledger c053 |
| 5.2 | `AGENTS.md` (conventions, gotchas, how to navigate) | ✅ | `AGENTS.md` (repo root) · Ledger c053 |
| 5.3 | ADR-0001 no-Docker / SQLite | ✅ | `kb/adr/ADR-0001…` · Ledger c051 |
| 5.4 | ADR-0002 append-only clinical records | ✅ | `kb/adr/ADR-0002…` · Ledger c051 |
| 5.5 | ADR-0003 JWT + bcrypt auth | ✅ | `kb/adr/ADR-0003…` · Ledger c021 (Phase 1) |
| 5.6 | ADR-0004 layered architecture | ✅ | `kb/adr/ADR-0004…` · Ledger c051 |
| 5.7 | ADR-0005 audit strategy | ✅ | `kb/adr/ADR-0005…` · Ledger c051 |
| 5.8 | `domain/glossary.md` | ✅ | authored in lockstep (c021), extended per phase |
| 5.9 | `domain/business-rules.md` (rules §5.1–§5.8 + why + edge cases) | ✅ | all 8 rules authored in lockstep (c034/c043/c050) · traceable to tests |
| 5.10 | `domain/access-matrix.md` (RBAC rationale per cell) | ✅ | authored in lockstep (c021) |
| 5.11 | `data/erd.md` (Mermaid ERD + rationale) | ✅ | `kb/data/erd.md` · Ledger c052 |
| 5.12 | `api/` OpenAPI export + contract notes | ✅ | `kb/api/openapi.json` + `README.md` · Ledger c052 |
| 5.13 | `workflows/` sequence diagrams (register, book, triage→consult, prescribe, cancel/no-show) | ✅ | all 5 done (c034/c043/c050/c052) |
| 5.14 | `runbooks/` (setup, seed, reset-db, troubleshooting, failure modes) | ✅ | `kb/runbooks/setup-and-operations.md` · Ledger c052 |
| **Exit** | KB complete & cross-linked; index navigable | ✅ | KNOWLEDGE-INDEX links all ADRs/rules/workflows/ERD/API/runbook · Ledger c053 |

---

## 8. Phase 6 — Tests, Seed Data, Polish

| # | Task | Status | Notes |
|---|---|---|---|
| 6.1 | Traceability: every §5 rule → named test (cross-referenced) | ✅ | `kb/domain/traceability.md` (§5.1–§5.8 → tests) · Ledger c055 |
| 6.2 | Rich seed dataset (patients/doctors/nurses, appts, history, rx) | ✅ | full clinical journey seeded idempotently · 1 test + live · Ledger c054 |
| 6.3 | Web route tests (`tests/web/`: status, auth redirects, role gating, key markup) | ✅ | `test_web_routes_sweep.py` (12) + per-feature web tests · Ledger c056 |
| 6.4 | README finalize (screenshots/flows, troubleshooting) | ✅ | demo accounts + feature summary + KB pointer · Ledger c057 |
| 6.5 | Rewrite stale `~/shared/webapp/PROJECT-BRIEF.md` to match | ✅ | rewritten for HealthyVytals · Ledger c057 |
| 6.6 | Final end-to-end verification (DESIGN.md §"Verification") | ✅ | fresh migrate+seed+boot; all 4 roles log in, seeded journey visible · Ledger c058 (fixed .local email bug) |
| **Exit** | Fresh clone → one command → seeded, working app; all tests green | ✅ | verified; 262 tests green · Ledger c058 |

---

## 8b. Phase 7 — Real role dashboards + UI shell (DESIGN §13, M7)

| # | Task | Status | Notes |
|---|---|---|---|
| 7.1 | App shell: vendored Pico.css + role-aware sidebar layout in `base.html`/`_base.html` | ✅ | Pico v2.1.1 vendored; app-shell + sidebar · Ledger c060 |
| 7.2 | Doctor dashboard: today's worklist + treated-patient list (wire existing services) | ✅ | B5, C5 · metrics + worklist table · Ledger c061 |
| 7.3 | Doctor: open-encounter entry from dashboard (review vitals → diagnose → prescribe) | ✅ | C2, D1 · `POST /clinical/appointments/{id}/open` · Ledger c061 |
| 7.4 | Nurse dashboard: ward board (today's appointments) + check-in action | ✅ | B5, B6 · ward board + check-in · Ledger c063 |
| 7.5 | Nurse: vitals-entry UI (currently API-only) | ✅ | C1, §5.5 · HTMX form + flagged result · Ledger c063 |
| 7.6 | Admin: user console (list / provision / activate-deactivate) | ✅ | E1 · `/admin/users` · Ledger c064 |
| 7.7 | Admin: audit-log viewer with filters (by user/patient/action) | ✅ | E2, E3, §5.7 · `/admin/audit` · Ledger c064 |
| 7.8 | Patient overview home (upcoming appts, active rx, recent activity) | ✅ | metric tiles + quick actions · Ledger c065 |
| 7.9 | Web route-test sweep for the new role pages | ✅ | admin routes + patient home · Ledger c065 |
| 7.10 | KB update: web-UI map / role-screens note | ✅ | `kb/web-ui-map.md` · Ledger c065 |
| **Exit** | Each role logs in to a working control center (no placeholders) | ✅ | live-verified all 4 roles · Ledger c065 |

## 8c. Phase 8 — Lab results & reports (DESIGN §13, M8)

| # | Task | Status | Notes |
|---|---|---|---|
| 8.1 | `LabOrder` + `LabResult` models (+ migration) | ✅ | `models/lab.py` + migration · 2 tests · Ledger c066 |
| 8.2 | Domain: result abnormal-flagging + visibility (reuse §5.3 scoping, §5.8 consent) | ✅ | `domain/lab_rules.py` · 7 tests · Ledger c067 (visibility reused in service) |
| 8.3 | Service: order lab (doctor) / record result (nurse/lab) / view (scoped) + audit | ✅ | `lab_service` + `lab_repository` · 5 tests · Ledger c068 |
| 8.4 | API endpoints (order, record, list by encounter/patient) | ✅ | `/api/v1/labs/*` · 3 tests · Ledger c068 |
| 8.5 | Web: doctor orders + reviews; nurse records; patient views results | ⬜ | HTMX |
| 8.6 | Tests (domain/service/api/web) + KB business rule + workflow diagram | ✅ | rule #9 + workflow + integration · Ledger c070 |
| **Exit** | Doctor orders → result recorded → patient & doctor view (abnormal flagged) | ✅ | integration test green · Ledger c070 |

## 8d. Phase 9 — Messaging & in-app notifications (DESIGN §13, M9)

| # | Task | Status | Notes |
|---|---|---|---|
| 9.1 | `Message`/thread + `Notification` models (+ migration) | ✅ | `models/messaging.py`, `models/notification.py` + rev `90dfe13e2800` · Ledger c071 |
| 9.2 | Service: send/list messages (care-team scoped); emit notifications on events | ✅ | `messaging_service` + `notification_service`; emission wired into appt/lab/rx paths · Ledger c071 |
| 9.3 | API endpoints (threads, messages, notifications read/mark-read) | ✅ | `api/v1/messages.py` · Ledger c071 |
| 9.4 | Web: message thread UI + notification feed (HTMX) in the app shell | ✅ | `web/messaging.py` + templates; sidebar links added · Ledger c071 |
| 9.5 | Tests + KB | ✅ | domain/service/api/web tests; Rule #10 + workflow diagram · Ledger c071 |
| **Exit** | Patient ↔ care-team messaging works; domain events raise notifications | ✅ | milestone gate — 320 tests green |

## 8e. Phase 10 — Documents & vitals trends (DESIGN §13, M10)

| # | Task | Status | Notes |
|---|---|---|---|
| 10.1 | `Document` model + local (git-ignored) storage + migration | ⬜ | upload/download |
| 10.2 | Service + API: upload/list/download, scoped | ⬜ | |
| 10.3 | Web: patient document area | ⬜ | |
| 10.4 | Vitals trend charts on history page | ✅ | Done c075 (M13) — Chart.js vendored per ADR-0007 (superseded the inline-SVG sketch) |
| 10.5 | Tests + KB | ⬜ | |
| **Exit** | Patient uploads/downloads docs; vitals trends render over time | ⬜ | milestone gate |

## 8f. Phase 11 — v2 polish, rich seed, e2e verification (DESIGN §13, M11)

| # | Task | Status | Notes |
|---|---|---|---|
| 11.1 | Seed the new domains (labs/messages/notifications/docs) for a full cross-role demo | ⬜ | |
| 11.2 | Cross-role e2e integration test (the §13.3 narrative) | ⬜ | |
| 11.3 | README + KB finalize for v2 | ⬜ | |
| 11.4 | Final v2 end-to-end verification | ⬜ | project gate |
| **Exit** | Fresh clone → one command → full-featured app, all roles, all tests green | ⬜ | v2 gate |

---

## 8g. Phase 12 — AI vitals assistant & LLM component layer (DESIGN §14, M12)

> The companion book's Chapter 2 worked example: wire an LLM into the app **as a system
> component**. Default provider is an offline deterministic stub, so the whole suite runs with
> no API key/SDK (ADR-0006). See Rule #11 + workflows/vitals-assistant.md.

| # | Task | Status | Notes |
|---|---|---|---|
| 12.1 | `core/llm` component layer: client (5 disciplines), providers (stub-default + opt-in anthropic/openai), errors, observability, schema base | ✅ | c072; offline-testable |
| 12.2 | LLM settings in `core/config` (provider, api key, tier→model routing, timeout/retries/cache) + `.env.example` | ✅ | c072 |
| 12.3 | `VitalsAssessment` output contract + `vitals_assistant_service` (rule-grounded, safe degradation, safety clamp, audit) | ✅ | c073 |
| 12.4 | Tests: component layer (15) + service (6), all offline/deterministic | ✅ | c072–c073; full suite 341 green |
| 12.5 | KB: Rule #11, ADR-0006, workflows/vitals-assistant.md, KNOWLEDGE-INDEX; DESIGN §14; README | ✅ | c072–c073 (lockstep) |
| 12.6 | Expose to users: API `POST /encounters/{id}/vitals-assessment` + `VitalsAssessmentOut`; service `assess_encounter_vitals` (age+latest reading, §5.3 authz) | ✅ | c074 |
| 12.7 | Nurse web UI: HTMX "Get AI triage assist" panel on the vitals screen + urgency-badge CSS | ✅ | c074 |
| 12.8 | Tests: API (5) + web (3) for the exposed endpoints; docs/ledger in lockstep | ✅ | c074; full suite 349 green |
| **Exit** | Vitals → structured advisory assessment, reachable via API **and** nurse UI; rule stays source of truth; real model works when keyed; offline by default; audited; suite green | ✅ | milestone gate — 349 tests green |

---

## 8h. Phase 13 — Vitals trends, booking UX & visual refresh (DESIGN §15, M13)

| # | Task | Status | Notes |
|---|---|---|---|
| 13.1 | Vitals-series read: `clinical_service.get_vitals_series` + `encounter_repository.vitals_for_patient` (scoped like history, §5.3/§5.8, audited) | ✅ | c075; Rule #12 |
| 13.2 | `GET /api/v1/patients/{id}/vitals-series` + `VitalsSeriesOut`; vendor Chart.js + ADR-0007; chart on history page (progressive enhancement) | ✅ | c075 |
| 13.3 | Booking UX: "My appointments" shows slot time + doctor + status pill (`scheduled_for_patient`); patient cancel via HTMX (`change_status` CANCEL); polished book page | ✅ | c076 |
| 13.4 | Visual refresh within the Pico shell: design tokens, elevation, hero, active-nav, status pills, dark-mode parity (no build step) | ✅ | c077 |
| 13.5 | Tests (vitals-series 4 + trends-web 1 + appointments 2) + KB (Rule #12, ADR-0007, workflows/vitals-trends.md) + README | ✅ | c075–c077; full suite 356 green |
| **Exit** | Patient sees vitals trends; improved booking with cancel; refreshed UI; all scoped/audited; suite green | ✅ | milestone gate — 356 tests green |

---

## 9. Cross-Cutting / Continuous (apply to every commit)

| Concern | Status | Notes |
|---|---|---|
| One functionality → one commit, journaled to ledger (§9A.1, §9A.6) | 🟡 Active | began at slice c001; recorded in `COMMIT_LEDGER.md` |
| Definition of Done met before commit (§9A.2) | 🟡 Active | applied from c001 onward |
| Principal-engineer quality bar (§9A.4) | 🟡 Active | correctness, security, clarity |
| KB updated in lockstep with code | 🟡 Active | never defer docs |
| Audit logging on all PHI access (§5.7) | ✅ Active | `record_audit` on all auth/appointment/clinical/prescription paths incl. failures |
| Honest status reporting in this file + commits | 🟡 Ongoing | flip statuses truthfully |
