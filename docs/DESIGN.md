# HealthyVytals — Engineering Design Document

> **Product name:** HealthyVytals (future domain: `HealthyVytals.ai`)

> **Status:** DRAFT — awaiting review
> **Owner:** Principal Engineer (AI-assisted build)
> **Last updated:** 2026-08-08
> **Audience:** A college grad or working software engineer who will clone this repo and run it locally on **Windows or macOS with no Docker**.

---

## 1. Problem Statement

Clinics need software to coordinate the everyday interaction between **patients, nurses, and doctors**: creating accounts, booking appointments, capturing vitals, recording diagnoses, prescribing medication, and letting each person see exactly the medical history they are entitled to — no more, no less.

We are building **HealthyVytals**, a local-first, full-stack medical portal that models this workflow end to end. It is deliberately *not* a thin CRUD demo. The system encodes the **non-obvious clinical and access-control rules** that make healthcare software hard, because the real goal of this project is to prove a hypothesis:

> **Hypothesis:** An AI that is given a *curated knowledge base* over this codebase can understand the system end-to-end and make correct changes, whereas an AI given only the raw source (as on a public GitHub repo) will produce shallow or wrong answers.

To make that provable, the domain must be rich in rules that **cannot be inferred from the code alone** — e.g. *why* clinical records are append-only, *why* a doctor can see one patient's full history but not another's, *what* the legal appointment state transitions are. Those rules live in code **and** in an authored knowledge base, kept in lockstep.

### Goals
1. A working three-layer app (Jinja2 + HTMX web UI → FastAPI backend → SQLite database).
2. Runnable by a beginner with **one command per OS**, no Docker, no DB server install.
3. Realistic, rule-heavy medical domain logic with a real domain layer (not anemic CRUD).
4. A large, high-value knowledge base (ADRs, glossary, business rules, ERD, workflows, runbooks).
5. Automated tests that pin every documented business rule.

### Non-Goals (explicitly out of scope for v1)
- Not HIPAA-certified or production-secure; it is an educational reference app.
- No real payment/insurance claim processing, no telehealth video, no messaging/chat.
- No external EHR/FHIR integration (the data model is FHIR-*inspired*, not FHIR-compliant).
- No real drug database; the drug-interaction/allergy checks use a curated seed list.
- No email/SMS delivery; notifications are represented in-app only.

---

## 2. Personas & Roles

| Role | Who they are | Primary needs |
|---|---|---|
| **Patient** | The person receiving care | Register, book/cancel appointments, view *their own* history, vitals, prescriptions |
| **Nurse** | Clinical staff who triages | Record vitals, view ward schedule, prep encounters for the doctor |
| **Doctor** | Licensed clinician | Manage availability, run consultations, diagnose, prescribe (with safety checks) |
| **Admin** | Clinic operations | Manage users, read the audit log; **no clinical authoring rights** (least-privilege) |

> **Why Admin exists** beyond the three roles requested: someone must administer accounts and read the PHI-access audit log. Giving that power to a clinical role would break least-privilege. Admin is intentionally *not* allowed to author diagnoses or prescriptions.

---

## 3. User Stories

Grouped by epic. Each story maps to an implementation phase (§8) and will map to tests (§10).

### Epic A — Accounts & Authentication
- **A1.** As a visitor, I can register as a patient with email + password so I can use the portal.
- **A2.** As staff (doctor/nurse/admin), an admin can provision my account with the correct role (staff are *not* self-service, mirroring real clinics).
- **A3.** As any user, I can log in and receive a session so subsequent requests are authenticated.
- **A4.** As any user, my session refreshes without re-entering my password until the refresh token expires.
- **A5.** As any user, I can only perform actions my role permits; forbidden actions return a clear 403.

### Epic B — Appointments
- **B1.** As a doctor, I can publish availability slots (day, time range, duration).
- **B2.** As a patient, I can see a doctor's open slots and book one with a reason for visit.
- **B3.** As a patient, I cannot book a slot that is already taken or that overlaps a doctor's buffer window.
- **B4.** As a patient, I can cancel my appointment before the cancellation cutoff; after that it's flagged late.
- **B5.** As a nurse/doctor, I can see the day's schedule for my ward / my calendar.
- **B6.** As staff, I can move an appointment through its lifecycle (check-in → in-progress → completed) and mark **no-show**.

### Epic C — Clinical Workflow & Medical History
- **C1.** As a nurse, I can record a patient's vitals for a visit; out-of-range values are flagged.
- **C2.** As a doctor, I can open an encounter, read the nurse's vitals, and record a diagnosis (ICD-style code + notes).
- **C3.** As a doctor, I can add a correction to a past record as an **addendum** (records are never edited in place).
- **C4.** As a patient, I can view my own complete history (encounters, diagnoses, vitals, prescriptions, allergies).
- **C5.** As a doctor, I can view the full history **only** of patients I have a treating relationship with.
- **C6.** As any PHI access, the system records who accessed which record and when (audit trail).

### Epic D — Prescriptions & Safety
- **D1.** As a doctor, I can prescribe a medication tied to an encounter.
- **D2.** The system **blocks** a prescription that conflicts with a recorded patient allergy.
- **D3.** The system **warns** on a known drug–drug interaction with the patient's active medications.
- **D4.** As a doctor, I can set refills within limits; controlled substances cap refills.
- **D5.** As a patient, I can view my active and past prescriptions.

### Epic E — Admin & Audit
- **E1.** As an admin, I can list/deactivate user accounts.
- **E2.** As an admin, I can read the audit log filtered by user, patient, or date.
- **E3.** As a non-admin, I cannot access the audit log at all.

---

## 4. Domain Model

### 4.1 Entities

| Entity | Key fields | Notes |
|---|---|---|
| **User** | id, email, password_hash, role, is_active | Base account; role discriminates behavior |
| **PatientProfile** | user_id, dob, sex, phone, insurance_id, emergency_contact | 1:1 with a PATIENT user |
| **DoctorProfile** | user_id, specialty, license_no | 1:1 with a DOCTOR user |
| **NurseProfile** | user_id, ward | 1:1 with a NURSE user |
| **AvailabilitySlot** | id, doctor_id, start, end, is_booked | A bookable window |
| **Appointment** | id, patient_id, doctor_id, slot_id, status, reason, created_at | State machine (§5.1) |
| **Encounter** | id, appointment_id, patient_id, doctor_id, opened_at, closed_at | The clinical visit record; append-only |
| **Vitals** | id, encounter_id, recorded_by, bp_sys, bp_dia, hr, temp_c, spo2, height_cm, weight_kg, flags | Entered by nurse |
| **Diagnosis** | id, encounter_id, author_id, icd_code, description, created_at | Append-only; corrections via addendum |
| **Addendum** | id, target_type, target_id, author_id, note, created_at | Immutable correction record |
| **Allergy** | id, patient_id, substance, reaction, severity | Drives prescription safety |
| **Medication** | id, name, drug_class, is_controlled | Curated seed catalog |
| **Prescription** | id, encounter_id, patient_id, prescriber_id, medication_id, dose, refills, status | Safety-checked on create |
| **DrugInteraction** | medication_a_id, medication_b_id, severity | Curated seed pairs |
| **AuditLog** | id, actor_id, action, resource_type, resource_id, patient_id, at | Written by middleware/service |

### 4.2 Entity-Relationship (overview)

```
User 1─1 {PatientProfile | DoctorProfile | NurseProfile}
Doctor 1─* AvailabilitySlot
Patient 1─* Appointment *─1 Doctor
Appointment 1─1 Encounter
Encounter 1─* Vitals
Encounter 1─* Diagnosis
Encounter 1─* Prescription *─1 Medication
Patient 1─* Allergy
Medication *─* Medication  (via DrugInteraction)
(any clinical record) 1─* Addendum
User 1─* AuditLog (as actor)
```

A full Mermaid ERD with rationale per relationship will live in `docs/knowledge-base/data/erd.md`.

---

## 5. Key Business Rules (the "knowledge base gold")

These are the rules an AI **cannot** guess from code. Each will be (a) enforced in the domain layer, (b) documented with its *why* in `docs/knowledge-base/domain/business-rules.md`, and (c) covered by a test.

### 5.1 Appointment State Machine
```
requested ──confirm──▶ confirmed ──check_in──▶ checked_in ──begin──▶ in_progress ──complete──▶ completed
   │                        │                      │
   └──cancel──▶ cancelled   └──cancel──▶ cancelled └──no_show──▶ no_show
confirmed/checked_in ──reschedule──▶ requested (new slot)
```
- Only **legal transitions** are allowed; illegal ones return 409.
- **Who** may trigger each transition is role-gated (patient can cancel; staff check-in; doctor completes).

### 5.2 Slot Conflict & Buffer
- A doctor cannot have two overlapping appointments.
- A configurable **buffer** (default 10 min, `APPOINTMENT_BUFFER_MINUTES`) is enforced between appointments.
- Cancellation within the **cutoff** (default 24h, `CANCELLATION_CUTOFF_HOURS`) is allowed but flagged late.

### 5.3 Treating-Relationship Scoping
- A doctor may read a patient's full history **only if** they have (or had) an appointment/encounter with that patient. Otherwise access is denied and the attempt is audited.

### 5.4 Prescription Safety
- **Hard block** if the medication (or its class) matches a recorded patient **allergy**.
- **Warn** (require explicit override flag) on a known **drug–drug interaction** with an active medication.
- **Controlled substances** cap the number of refills.

### 5.5 Vitals Normal Ranges
- Normal ranges vary by patient **age**; out-of-range readings set a `flags` field, which surfaces the encounter for attention.

### 5.6 Immutable Clinical Records
- Encounters, diagnoses, and prescriptions are **append-only**. A mistake is corrected by an **Addendum**, never an in-place edit — preserving the legal record (analogous to accounting reversing entries).

### 5.7 Mandatory Audit Logging
- Every **read or write of PHI** writes an `AuditLog` row (actor, action, resource, patient, timestamp) via a cross-cutting mechanism.

### 5.8 Consent Gating (v1: simple flag)
- Sensitive categories (e.g. mental-health notes) carry a consent flag; without consent they are excluded from views even for otherwise-authorized staff.

---

## 6. Access-Control Matrix

Enforced by route guards (coarse) + service-layer ownership checks (fine). Rationale per cell in `docs/knowledge-base/domain/access-matrix.md`.

| Resource / Action | Patient | Nurse | Doctor | Admin |
|---|---|---|---|---|
| Own profile (R/W) | ✅ | ✅ | ✅ | ✅ |
| Register self | ✅ | — | — | — |
| Provision staff account | — | — | — | ✅ |
| Patient demographics | own | assigned ward | treating patients | all |
| Availability slots | read | read | **create own** | read |
| Book / cancel appointment | **own** | on behalf (ward) | own calendar | all |
| Advance appointment state | — | check-in | begin/complete/no-show | — |
| Vitals | read own | **create/read** | read | read |
| Diagnosis | read own | read | **create** | read |
| Prescription | read own | read | **create (safety-checked)** | read |
| Addendum | — | on own entries | on own entries | — |
| Audit log | — | — | — | **read** |

---

## 7. Architecture & Components

### 7.1 High-level
```
┌──────────────────────────────────────────────────┐      SQL      ┌──────────┐
│              FastAPI app  (one process, :8000)     │ ────────────▶ │  SQLite  │
│                                                    │ ◀──────────── │  file DB │
│  web/ (Jinja2+HTMX, HTML)   api/v1/ (JSON)         │               └──────────┘
│         └──────────┬──────────┘                    │
│              services → domain → repositories      │
└──────────────────────────────────────────────────┘
        ▲ browser: HTML + HTMX partials, HttpOnly cookie session
```

### 7.2 Backend layering (dependencies point inward)
- **api/** — FastAPI routers; HTTP concerns only (parse, authorize via guards, shape responses).
- **schemas/** — Pydantic v2 request/response models (validation + serialization boundary).
- **services/** — use-case orchestration; transactions; calls domain + repositories.
- **domain/** — pure business rules: state machine, safety checks, vitals ranges, scoping. **No framework/DB imports** — unit-testable in isolation.
- **repositories/** — data-access layer (DAL/DAO); the **only** place that queries the DB.
- **models/** — SQLAlchemy ORM entities.
- **db/** — engine/session/unit-of-work, seed data.
- **core/** — config, security (JWT/hashing), dependencies, RBAC roles, typed errors, audit.

> **Why a separate `domain/` layer:** it lets the hardest, most rule-heavy logic be tested without a database or HTTP, and it's the natural place the knowledge base points to. This is what separates the app from anemic CRUD.
>
> **Why a separate `repositories/` layer:** confining all queries to one layer keeps the
> persistence engine swappable (SQLite↔Postgres), makes data access independently testable,
> and gives audit/scoping a single choke point. The full folder contract and layering rules
> are in §7.5–§7.6.

### 7.3 Frontend — Server-rendered Jinja2 + HTMX (CONFIRMED §12.1)

**Decision:** the UI is **server-rendered with Jinja2 templates + HTMX**, served *by the
FastAPI app itself*. There is **no React, no Vite, and no Node.js prerequisite** — the single
biggest setup-friction remover for the "college grad on Windows" goal. The whole product runs
as **one process on `:8000`**.

- **Rendering:** FastAPI route handlers return HTML via `Jinja2Templates`. Templates live in
  `backend/app/web/templates/`; static assets (a little CSS, the HTMX script) in
  `backend/app/web/static/`.
- **Interactivity:** HTMX attributes (`hx-get`, `hx-post`, `hx-target`, `hx-swap`) issue
  AJAX-style requests and swap in server-rendered HTML **partials** — no client-side SPA, no
  build step. Progressive enhancement: forms work even where JS is limited.
- **Auth in the browser:** because pages are server-rendered, the session token is carried in
  an **HttpOnly cookie** (set at login, cleared at logout), not localStorage — this avoids
  XSS token theft and needs no JS to attach headers. The JSON API (§7.6) still accepts a
  `Bearer` token for programmatic/testing use; the web UI uses the cookie. Both resolve to the
  same `get_current_user` dependency.
- **Role-aware views:** after login the user lands on a Patient / Nurse / Doctor / Admin
  dashboard. Templates are organized per role + shared partials.
- **Pages:** Login/Register, Dashboard (per role), Book Appointment, Appointment/Encounter
  detail, Medical History, Prescriptions, Admin (Users + Audit Log).

> **Design consequence — thin web layer, not a second brain:** the `web/` layer is a
> presentation concern only. It calls the **same services** the JSON API calls; it contains no
> business logic and no direct DB access (same rules as §7.6). A web route may compose a couple
> of service calls and render a template, nothing more. This keeps a single source of truth for
> behavior whether accessed via HTML or JSON.
>
> **Why HTMX over a SPA here:** it delivers real interactivity (partial updates, no full-page
> reloads) while keeping the stack pure-Python and buildless — which is exactly the local-first,
> low-prerequisite bar this project targets. A future React client remains possible precisely
> *because* the JSON API and services already exist independently.

### 7.4 Cross-cutting: Audit
- Implemented as a service-layer helper invoked by every PHI read/write path, plus optional middleware for coarse request logging. Service-layer is authoritative because only there is the affected `patient_id` known.

### 7.5 Repository Structure (single monolith repo)

This is **one repository** — a modular monolith. Everything (backend, server-rendered web UI,
docs, scripts, tests) lives here. Because the UI is Jinja2 + HTMX served by FastAPI (§7.3),
there is **no separate `frontend/` project and no Node toolchain** — the presentation layer is
`backend/app/web/`. The layout below is a **hard contract**: new code goes in the layer that
owns its concern; we do not collapse layers to save keystrokes. Every layer is separated so
responsibilities are unmistakable and the codebase reads like a product, not a prototype.

```
healthyvytals/
├── README.md                         # prereqs, one-command run, troubleshooting
├── Makefile                          # macOS/Linux task shortcuts (mirror of scripts/)
├── .gitignore
├── .env.example                      # documented env vars; real .env is git-ignored
│
├── backend/
│   ├── requirements.txt              # runtime + dev dependencies (pinned)
│   ├── pyproject.toml                # tool config: pytest, ruff/black, mypy
│   ├── alembic.ini                   # migration config (if Alembic chosen)
│   ├── alembic/                      # migration environment + versioned scripts
│   │   └── versions/
│   ├── app/
│   │   ├── main.py                   # app factory, middleware wiring, router mount
│   │   ├── core/                     # cross-cutting: config, security, roles, deps, errors, logging
│   │   │   ├── config.py             #   env-driven Settings
│   │   │   ├── security.py           #   hashing + JWT
│   │   │   ├── roles.py              #   Role enum + RBAC groupings
│   │   │   ├── deps.py               #   FastAPI dependencies (get_current_user, require_roles, get_db)
│   │   │   ├── errors.py             #   domain exception types + HTTP exception handlers
│   │   │   └── audit.py              #   audit context helper
│   │   │
│   │   ├── api/                      # HTTP LAYER ONLY — thin controllers, no business logic
│   │   │   ├── router.py             #   aggregates all versioned routers
│   │   │   └── v1/                   #   API is versioned from day one (/api/v1/...)
│   │   │       ├── auth.py
│   │   │       ├── users.py
│   │   │       ├── appointments.py
│   │   │       ├── encounters.py
│   │   │       ├── prescriptions.py
│   │   │       └── audit.py
│   │   │
│   │   ├── schemas/                  # API MODELS (Pydantic v2) — request/response shapes
│   │   │   ├── common.py             #   shared: Page[T], ErrorResponse, ORM base config
│   │   │   ├── auth.py               #   RegisterRequest, LoginRequest, TokenPair, ...
│   │   │   ├── user.py               #   UserCreate, UserOut, ProfileOut, ...
│   │   │   ├── appointment.py
│   │   │   ├── encounter.py
│   │   │   └── prescription.py
│   │   │
│   │   ├── services/                 # APPLICATION LAYER — use-case orchestration + transactions
│   │   │   ├── auth_service.py
│   │   │   ├── appointment_service.py
│   │   │   ├── clinical_service.py
│   │   │   ├── prescription_service.py
│   │   │   └── audit_service.py
│   │   │
│   │   ├── domain/                   # DOMAIN LAYER — pure rules, NO framework/DB imports
│   │   │   ├── appointment_state.py  #   state machine (§5.1)
│   │   │   ├── scheduling_rules.py   #   conflict/buffer/cutoff (§5.2)
│   │   │   ├── access_scope.py       #   treating-relationship scoping (§5.3)
│   │   │   ├── prescription_safety.py#   allergy/interaction/refill (§5.4)
│   │   │   └── vitals_ranges.py      #   age-based ranges + flags (§5.5)
│   │   │
│   │   ├── models/                   # PERSISTENCE MODELS — SQLAlchemy 2.0 ORM entities
│   │   │   ├── base.py               #   DeclarativeBase, timestamp mixin, id mixin
│   │   │   ├── user.py
│   │   │   ├── profile.py
│   │   │   ├── scheduling.py
│   │   │   ├── clinical.py
│   │   │   ├── prescription.py
│   │   │   └── audit.py
│   │   │
│   │   ├── repositories/             # DATA-ACCESS LAYER (DAL/DAO) — the ONLY place that queries the DB
│   │   │   ├── base.py               #   generic Repository[Model] (get/list/add/…)
│   │   │   ├── user_repository.py
│   │   │   ├── appointment_repository.py
│   │   │   ├── encounter_repository.py
│   │   │   └── prescription_repository.py
│   │   │
│   │   ├── db/                       # engine, Session factory, unit-of-work, seed data
│   │   │   ├── session.py
│   │   │   └── seed.py
│   │   │
│   │   └── web/                      # PRESENTATION LAYER — server-rendered Jinja2 + HTMX (§7.3)
│   │       ├── router.py             #   HTML routes; call services, render templates. No logic/DB.
│   │       ├── deps.py              #   cookie-session → current user (mirrors api deps)
│   │       ├── templates/            #   Jinja2 templates
│   │       │   ├── base.html         #     layout (loads htmx.min.js + app.css)
│   │       │   ├── auth/             #     login.html, register.html
│   │       │   ├── dashboard/        #     patient.html, nurse.html, doctor.html, admin.html
│   │       │   ├── appointments/     #     list/detail/book + partials
│   │       │   ├── encounters/       #     vitals, diagnosis, history + partials
│   │       │   ├── prescriptions/
│   │       │   ├── admin/            #     users, audit-log
│   │       │   └── partials/         #     HTMX-swappable fragments (rows, flash, modals)
│   │       └── static/               #   app.css, htmx.min.js (vendored — no CDN/Node)
│   │
│   └── tests/                        # mirrors app/ layout
│       ├── conftest.py               #   fixtures: temp DB, client, seeded users
│       ├── domain/                   #   pure unit tests (fast, no DB)
│       ├── services/                 #   service tests (DB, no HTTP)
│       ├── api/                      #   JSON API integration tests (HTTP → DB)
│       └── web/                      #   HTML/HTMX route tests (status, key markup, auth redirects)
│
├── scripts/                          # setup.ps1/.sh, dev.ps1/.sh, reset-db.*, seed.*
│
└── docs/
    ├── DESIGN.md
    ├── TASKS.md
    └── knowledge-base/               # ADRs, glossary, business-rules, access-matrix, ERD, workflows, runbooks
```

### 7.6 Layering & Abstraction Rules (enforced every commit)

The request flow is strictly one-directional; dependencies point inward and never skip
or reverse:

```
HTTP request
   → api/v1/*  (JSON)   ┐
   → web/*     (HTML)   ┘ both entrypoints validate input, authorize via deps, call a service
   → services/*         (orchestrate the use case, open a transaction/unit-of-work)
   → domain/*           (apply pure business rules — decisions, no I/O)
   → repositories/*     (the ONLY layer that talks to the DB, via models)
   → models/ + db/      (ORM entities + session)
```

Both the JSON API (`api/v1/`) and the server-rendered web UI (`web/`) are **thin entrypoints
over the same services** — the API returns Pydantic-serialized JSON, the web layer renders a
Jinja2 template with the same data. Neither contains business logic or DB access.

**Non-negotiable rules:**
1. **No business logic in routers.** `api/` only parses/validates (Pydantic), authorizes
   (guards), calls one service method, and shapes the response. If a router contains an
   `if` about domain state, it's in the wrong layer.
2. **No raw DB access outside `repositories/`.** Services and domain never build queries or
   touch `Session` directly; they go through a repository. This keeps persistence swappable
   (SQLite↔Postgres) and queries testable/auditable.
3. **`domain/` is pure.** No imports of FastAPI, SQLAlchemy, or `Session`. It takes plain
   data / value objects and returns decisions. This is what makes the hard rules unit-testable
   and is the heart of the "high-quality product" bar.
4. **Schemas ≠ ORM models.** API models (`schemas/`) are a deliberate boundary distinct from
   persistence models (`models/`). We never serialize ORM objects directly to clients; we map
   to explicit response schemas. This prevents accidental PHI/field leakage.
5. **API is versioned from day one** (`/api/v1`). Response envelope, pagination (`Page[T]`),
   and error shape (`ErrorResponse` with a stable `code`) are standardized in
   `schemas/common.py` so every endpoint looks and behaves consistently.
6. **Errors are typed.** Domain/service raise semantic exceptions (e.g. `IllegalTransition`,
   `SlotConflict`, `AllergyConflict`); `core/errors.py` maps each to the right HTTP status +
   stable error code. Handlers never leak stack traces or internal messages.
7. **Web layer is presentation-only.** `web/` routes render Jinja2 templates from service
   results; they hold no business logic and never touch repositories/DB directly (same rule as
   the API). Templates contain markup + HTMX attributes only — no domain decisions in templates.
   Reusable fragments live in `templates/partials/` and are the unit HTMX swaps.

> **Standard, not shortcut:** these abstractions exist even where a smaller app "could" skip
> them, because the goal is a product-grade, knowledge-base-rich codebase. When a task could
> be done quickly-but-shabbily or properly-but-slower, we **always choose properly** (see
> §9A.4). Slower and correct beats fast and brittle.

---

## 8. Local Run Design (no Docker)

- **One process, one port.** Because the UI is server-rendered by FastAPI (§7.3), the entire
  app — HTML pages, HTMX partials, and JSON API — is served by **Uvicorn on `:8000`**. There
  is no second dev server and no proxy.
  - Web UI: `http://localhost:8000/`
  - JSON API + interactive OpenAPI docs: `http://localhost:8000/docs`
- **Database:** SQLite file `backend/healthyvytals.db`, created and migrated on setup. Postgres
  is opt-in via `DATABASE_URL` (§12.2) with no code changes.
- **Migrations:** **Alembic**, wrapped in one-command scripts so a beginner never types raw
  Alembic. `scripts/migrate.*` runs `alembic upgrade head`; `scripts/reset-db.*` drops the
  SQLite file and re-migrates + re-seeds. Autogenerated revisions are reviewed, never blindly
  committed (§12.5).
- **Scripts (one command per OS):**
  - **Windows:** `scripts/setup.ps1` (create venv → `pip install` → `alembic upgrade head` →
    seed), then `scripts/dev.ps1` (launch Uvicorn with autoreload).
  - **macOS/Linux:** `scripts/setup.sh` then `scripts/dev.sh`. A `Makefile` mirrors these
    (`make setup`, `make dev`, `make reset-db`, `make test`).
  - `scripts/seed.*` and `scripts/reset-db.*` for convenience.
- **Prerequisites:** **Python 3.11+ only.** No Node.js, no Docker. (HTMX is a single vendored
  JS file served as a static asset — nothing to install or build.) Documented in README with
  install links.

---

## 9. Implementation Plan (phases & tasks, in order)

Each phase ends with something runnable and its knowledge-base docs updated. The
phases below are **milestones**, not commits. The unit of work is a single
functionality, delivered as a single commit — see the **Execution Methodology (§9A)**,
which governs *how* every task in this plan is built.

**Phase 0 — Scaffolding & local run** *(not started; see TASKS.md §2 for granular rows)*
- Repo layout; `requirements.txt`; `pyproject.toml`; `.gitignore`; `.env.example`.
- Core config/roles/security; DB session + `Base`; SQLite wiring; Alembic init + one-command wrapper.
- FastAPI app factory + `/health` + versioned `/api/v1` router; common API primitives + typed errors.
- `web/` bootstrap: Jinja2 templating + `base.html` + vendored HTMX; a rendered landing page.
- Setup/dev scripts for Windows + macOS; README quick-start.
- **Exit:** `scripts/dev.*` boots the single-process app on `:8000` (web UI + `/docs`) on both OSes.

**Phase 1 — Accounts & RBAC**
- User + profile models; register/login/refresh; JWT guards; audit scaffolding; seed users.
- **Exit:** all four roles can log in; forbidden actions return 403; audit rows appear.

**Phase 2 — Availability & appointments**
- Slots; appointment state machine; conflict/buffer/cancellation rules; booking UI + dashboards.
- **Exit:** patient books, staff advances state; double-book/late-cancel blocked.

**Phase 3 — Clinical workflow & history**
- Encounter; vitals (nurse) with range flags; diagnosis (doctor); addenda; history views with scoping.
- **Exit:** nurse→doctor flow works; scoping + append-only enforced.

**Phase 4 — Prescriptions & safety**
- Medication/allergy/interaction seed; prescribe with allergy block + interaction warn + refill caps.
- **Exit:** unsafe prescription blocked with a clear error; safe one succeeds.

**Phase 5 — Knowledge base authoring (finalize; kept in lockstep throughout)**
- ADRs, glossary, business-rules catalog, access matrix, ERD, sequence diagrams, runbooks, KNOWLEDGE-INDEX + AGENTS.md.

**Phase 6 — Tests, seed data, polish**
- pytest for every rule in §5; rich seed dataset (a few patients/doctors/nurses, appointments, history); README finalize; rewrite the old PROJECT-BRIEF.md to match.

---

## 9A. Execution Methodology (how we build — not what)

This section is a **hard contract on process**, not a suggestion. It exists to protect
two things: (1) the AI's working context, and (2) the quality bar demanded by
principal-engineer code review.

### 9A.1 One functionality → one commit (incremental delivery)

- We implement **exactly one functionality at a time** and produce **one focused commit**
  for it before moving on. A "functionality" is a vertical slice small enough to review
  in one sitting (e.g. "register a patient", "book an appointment", "block a prescription
  that conflicts with an allergy") — typically model + schema + service/domain rule +
  route + tests + doc update for that one capability.
- We do **not** batch multiple functionalities into a single large change.

**Why this ordering (the context-preservation rationale):**
> If we build everything at once, the AI assistant eventually exhausts its context
> window. The harness then summarizes older turns, and that summarization **loses core
> context** — subtle decisions, invariants, and half-finished threads get compressed
> away, and the assistant becomes distracted or inconsistent. Small, committed slices
> mean each unit of work fits comfortably in context, and every completed slice is
> **durably captured in git** (code + message) rather than living only in fragile
> conversation memory. Progress is slower per step but **monotonic and recoverable**:
> we can always reconstruct state from the commit history, not from a summary.

### 9A.2 Definition of Done for each commit

A functionality is not "done" — and no commit is made — until **all** of the following hold:

1. **Compiles / imports cleanly** and the app still starts.
2. **Tests exist and pass** for the new behavior, including the relevant §5 business rule
   and at least one failure/edge case (not just the happy path).
3. **Full test suite is green** (`pytest`), not just the new tests — no regressions.
4. **Knowledge base updated in lockstep** — if the slice touches a rule/entity/endpoint,
   the corresponding `docs/knowledge-base/` file is updated in the *same* commit.
5. **Self-review pass** against the checklist in §9A.4 before committing.
6. **Commit message** explains *what* and *why* (see §9A.3).

### 9A.3 Commit conventions

- Conventional-commit style: `feat(appointments): enforce doctor double-booking buffer`,
  `fix(auth): reject refresh token used as access token`, `docs(kb): add ADR-0002`.
- Body states the rationale and references the design/rule (e.g. "implements §5.2;
  see business-rules.md rule #2") so history is self-documenting for future AI/humans.
- One logical change per commit. No unrelated drive-by edits.

### 9A.4 Quality bar — assume aggressive principal-engineer review

Every commit is written **as if a panel of principal engineers will review it** and
critical, reputation-affecting feedback follows any sloppy, buggy, or unclear code.
Concretely, before each commit we verify:

- **Correctness first:** logic matches the documented rule; edge cases and error paths
  are handled, not just the happy path. No off-by-one, no unguarded `None`, no race in
  the "last slot" booking path.
- **Security:** no auth bypass; least-privilege enforced; no secrets in code; input
  validated at the boundary (Pydantic); no SQL built by string concatenation.
- **Clarity & altitude:** clear names; functions do one thing; comments explain *intent
  and rationale* at non-obvious decision points (the knowledge-base ethos), not the
  obvious.
- **Consistency:** matches existing patterns, layering (§7.2), and naming already in the
  repo. Domain layer stays free of framework/DB imports.
- **No dead weight:** no unused code, no TODOs left dangling, no commented-out blocks.
- **Tested:** meaningful assertions; tests would actually fail if the behavior broke.
- **Honest status:** if something is incomplete or a shortcut was taken, it is called
  out explicitly in the commit body — never presented as finished.

### 9A.5 Working rhythm per slice

`pick smallest next functionality → write domain/rule + test → wire service + route →
run full suite → update KB docs → self-review (§9A.4) → record commit in ledger (§9A.6)
→ report → next.`

After each commit the assistant gives a one-line status and the next intended slice, so
the human can redirect before the next unit of work begins.

### 9A.6 Deferred-commit ledger (no git yet)

Git is **not** initialized in this environment yet. Until it is, we do **not** lose the
one-commit-per-functionality discipline — we record each intended commit in a structured
**commit ledger** so the exact history can be replayed later by another AI or by a script.

- **Ledger file:** `docs/COMMIT_LEDGER.md` (human-readable) backed by a machine-readable
  `docs/commits/ledger.json` (source of truth for replay).
- **One ledger entry = one commit = one functionality.** Entries are append-only and
  strictly ordered; the order **is** the intended commit order.
- Each entry records: a sequence number, the exact **commit message** (subject + body,
  Conventional-Commits per §9A.3), the **ordered list of files** to `git add` for that
  commit, the functionality/task IDs it satisfies (e.g. `0.6`, rule `§5.2`), and a short
  rationale.
- **Workflow contract:** the moment a slice meets the Definition of Done (§9A.2), the
  assistant (a) writes/updates the actual source files on disk, and (b) appends a matching
  ledger entry in the **same** working step. Files on disk and ledger stay in perfect sync.
- **Replay (once git exists):** a human hands `ledger.json` (or `COMMIT_LEDGER.md`) to an
  AI/script that, for each entry in order, runs `git add <files>` then
  `git commit -m "<message>"`. The result is a clean, linear, self-documenting history
  that shows exactly how the app was built, one functionality at a time.
- **Amendments:** if a later slice must modify files from an earlier entry, that is a
  **new** ledger entry (a new commit), never an edit of a past entry — mirroring how git
  history is immutable. This keeps the replay honest.

> This mechanism is a temporary stand-in for git, but it enforces the *same* rigor: small,
> ordered, well-messaged, file-scoped commits. When git is initialized the transition is
> mechanical and lossless. See `docs/commits/README.md` for the exact JSON schema and the
> replay procedure.

---

## 10. Testing Strategy

- **Domain unit tests** (no DB): state-machine legality, vitals ranges, safety checks, scoping predicate.
- **API integration tests** (`httpx`/TestClient against a temp SQLite): auth flows, RBAC 403s, booking conflicts, prescription block, audit row creation.
- **Traceability:** each business rule in §5 → at least one named test, cross-referenced in `business-rules.md`.
- **Web UI:** HTTP-level tests (`tests/web/`) that hit the HTML routes via TestClient and
  assert status codes, auth redirects (unauthenticated → login), role gating, and the presence
  of key markup / HTMX attributes in rendered templates. No JS engine needed — we test the
  server-rendered output, which is where all logic lives.

---

## 11. Knowledge Base Deliverables (`docs/knowledge-base/`)

- `adr/` — e.g. ADR-0001 no-Docker/SQLite, ADR-0002 append-only clinical records, ADR-0003 JWT+bcrypt auth, ADR-0004 layered architecture, ADR-0005 audit strategy.
- `domain/glossary.md`, `domain/business-rules.md`, `domain/access-matrix.md`
- `data/erd.md` (Mermaid + rationale)
- `api/` (OpenAPI export + contract notes)
- `workflows/` (Mermaid sequence diagrams: register, book, triage→consult, prescribe, cancel/no-show)
- `runbooks/` (setup, seed, reset-db, troubleshooting, failure modes)
- `KNOWLEDGE-INDEX.md` + `AGENTS.md` — the map an AI reads first.

---

## 12. Decisions — CONFIRMED (2026-08-08)

All five open decisions are now settled. These are locked for v1.

1. **Frontend:** ✅ **Pure-Python Jinja2 + HTMX, server-rendered by FastAPI. No Node, no
   React, no build step.** The whole app runs as one process on `:8000`. (See §7.3.)
2. **Database default:** ✅ **SQLite** file by default; **Postgres opt-in** via `DATABASE_URL`
   with no code changes. (See §8.)
3. **Admin role:** ✅ **Included.** Admin manages users + reads the audit log; it has **no**
   clinical authoring rights (least-privilege). (See §2, §6.)
4. **v1 scope:** ✅ **Epics A–E as written in §3.** Lab results, notifications, and billing are
   explicitly **out of scope for v1** (Non-Goals, §1).
5. **Migrations:** ✅ **Alembic**, wrapped in one-command scripts (`scripts/migrate.*`,
   `scripts/reset-db.*`) so beginners never type raw Alembic. (See §8.)

---

*Decisions locked. The phased build proceeds per §9 (plan) and §9A (methodology), with each
functionality journaled to the commit ledger (§9A.6) and the knowledge base kept in lockstep.*
