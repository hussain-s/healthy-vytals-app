# HealthyVytals — Commit Ledger (human-readable)

> **What this is:** an ordered, append-only record of every intended git commit, created
> while git is not yet initialized. It is the human-readable mirror of
> `docs/commits/ledger.json` (the machine-readable source of truth used for replay).
> See `docs/commits/README.md` for the schema and the replay procedure, and `DESIGN.md`
> §9A.6 for the methodology.
>
> **Rules:** one entry = one commit = one functionality · strictly ordered · append-only
> (never edit past entries; to change earlier files, add a new entry) · files listed are
> exactly what to `git add` for that commit.
>
> **Status:** 77 commits recorded — Phases 0–6 complete; v2: M7–M9 done, M12 (AI vitals
> assistant, incl. API + nurse UI exposure) done, M13 (vitals trends, booking UX, visual
> refresh) done; M10 (documents) partial — trends done, documents remain; M11 remains.

---

<!--
Entry template (copy for each new commit):

## [seq] cNNN — <subject>

- **Commit message:**
  ```
  <type>(<scope>): <subject>

  <body — the why; refs TASKS ids and DESIGN sections>
  ```
- **Files (in add order):**
  - `path/one`
  - `path/two`
- **Satisfies:** TASKS <ids> · **Rules:** DESIGN <refs> · **Phase:** N
- **Depends on:** [seqs] (or none)
- **Rationale:** <one line>
-->

## [1] c001 — chore(repo): scaffold project root, env template, and toolchain

- **Commit message:**
  ```
  chore(repo): scaffold project root, env template, and toolchain

  Establishes the monolith's root scaffolding as the first committed slice.

  - .gitignore: ignore venvs, the runtime SQLite file, tool caches, and the real
    .env, while keeping .env.example tracked.
  - .env.example: documents every environment variable with safe placeholder
    defaults (SQLite by default per decision 12.2; JWT + domain tunables per 5.2).
  - backend/requirements.txt: pinned runtime + test dependencies (FastAPI,
    SQLAlchemy, Alembic, Jinja2, python-jose, passlib, pytest). No Node (12.1).
  - backend/pyproject.toml: pytest, ruff (lint+format+imports), and mypy config.

  Implements TASKS 0.1, 0.2, 0.17.
  Refs: DESIGN 7.5 (folder contract), 8 (local run), 12.1, 12.2, 12.5.
  ```
- **Files (in add order):**
  - `.gitignore`
  - `.env.example`
  - `backend/requirements.txt`
  - `backend/pyproject.toml`
- **Satisfies:** TASKS 0.1, 0.2, 0.17 · **Rules:** DESIGN §7.5, §8, §12.1, §12.2, §12.5 · **Phase:** 0
- **Depends on:** none
- **Rationale:** Root scaffolding + pinned deps + tool config — the base every later slice builds on.

## [2] c002 — feat(core): add env-driven application settings

- **Commit message:**
  ```
  feat(core): add env-driven application settings

  Introduces app.core.config.Settings — the single source of truth for
  runtime configuration, loaded from HV_-prefixed environment variables / .env
  with safe local defaults so a fresh clone runs with no .env.

  - SQLite is the default database (decision 12.2); Postgres is opt-in purely via
    HV_DATABASE_URL with no code changes.
  - Domain tunables (appointment buffer, cancellation cutoff) are centralized here
    so the 5.2 rules read thresholds from config, not magic numbers.
  - Production safety: refuses to boot when HV_ENV=production still uses the
    insecure placeholder JWT secret, preventing forgeable sessions.
  - get_settings() caches the Settings singleton (parsed once per process).
  - Adds app/ and app/core/ package docstrings (partial TASKS 0.11).

  Tests: defaults, HV_ overrides + type coercion, and the production secret guard
  (4 tests, all green).

  Implements TASKS 0.3 (and part of 0.11).
  Refs: DESIGN 7.2, 8, 5.2, 12.2.
  ```
- **Files (in add order):**
  - `backend/app/__init__.py`
  - `backend/app/core/__init__.py`
  - `backend/app/core/config.py`
  - `backend/tests/__init__.py`
  - `backend/tests/core/__init__.py`
  - `backend/tests/core/test_config.py`
- **Satisfies:** TASKS 0.3, 0.11 (partial) · **Rules:** DESIGN §7.2, §8, §5.2, §12.2 · **Phase:** 0
- **Depends on:** [1]
- **Rationale:** Central env-driven config with SQLite default + production secret guard; every layer reads settings from here.

## [3] c003 — feat(core): define roles and coarse RBAC groupings

- **Commit message:**
  ```
  feat(core): define roles and coarse RBAC groupings

  Adds app.core.roles: the authoritative Role enum (patient/nurse/doctor/
  admin) plus immutable frozenset groupings used by coarse route guards.

  The groupings encode non-obvious design decisions and are documented with their
  rationale (the knowledge-base ethos):
  - CLINICAL_AUTHORS = {doctor} only — nurses record vitals but do not author
    diagnoses/prescriptions; admin never authors clinical data (least-privilege).
  - AUDIT_READERS = {admin} only — separation of duties for the PHI audit log.
  - CLINICAL_STAFF / STAFF for the common 'clinician' vs 'internal staff' splits.

  Role subclasses str so it serializes as a plain value across JSON, JWTs, and the
  DB. Module is dependency-free (stdlib only) so any layer can import it without
  cycles. Fine-grained ownership/treating-relationship checks (5.3) deliberately
  live in the service layer, not here.

  Tests pin each grouping's membership so widening a set fails loudly (6 tests).

  Implements TASKS 0.4.
  Refs: DESIGN 6, 2, 5.3, 5.7.
  ```
- **Files (in add order):**
  - `backend/app/core/roles.py`
  - `backend/tests/core/test_roles.py`
- **Satisfies:** TASKS 0.4 · **Rules:** DESIGN §6, §2, §5.3, §5.7 · **Phase:** 0
- **Depends on:** [2]
- **Rationale:** Authoritative roles + RBAC groupings underpinning every guard in Phase 1.

## [4] c004 — feat(core): add password hashing and JWT security primitives

- **Commit message:**
  ```
  feat(core): add password hashing and JWT security primitives

  Adds app.core.security: the low-level auth crypto boundary, framework- and
  DB-agnostic.

  - hash_password/verify_password: bcrypt via passlib; salt+cost embedded in the
    hash. verify is constant-time and returns False (never raises) on a malformed
    stored hash.
  - create_access_token/create_refresh_token/decode_token: JWTs with sub/type/iat/
    exp. decode_token enforces signature, expiry, AND the expected token 'type',
    so an access token can't be replayed as a refresh token or vice versa
    (story A4). Reserved claims can't be overridden by extra_claims.
  - TokenError is intentionally coarse (no reason leak); errors.py will map it 401.

  Also pins bcrypt~=4.0.1 in requirements.txt: passlib 1.7.4 reads
  bcrypt.__about__.__version__, which bcrypt 4.1 removed; the 4.0.x line is what
  passlib supports. (requirements.txt legitimately reappears from c001 per the
  ledger's append-only, files-may-recur rule.)

  Tests (10): hashing salt/verify/malformed, access+refresh round-trip, both
  type-mismatch rejections, tampered-key rejection, backdated-expiry rejection,
  reserved-claim guard. Full suite: 20 passed.

  Implements TASKS 0.5.
  Refs: DESIGN 3 (A3, A4), 7.2.
  ```
- **Files (in add order):**
  - `backend/app/core/security.py`
  - `backend/tests/core/test_security.py`
  - `backend/requirements.txt`
- **Satisfies:** TASKS 0.5 · **Rules:** DESIGN §3 (A3, A4), §7.2 · **Phase:** 0
- **Depends on:** [2]
- **Rationale:** Password hashing + typed JWTs (access/refresh) — the crypto boundary auth flows build on.
- **Note:** `requirements.txt` reappears from c001 (bcrypt pin), which the ledger permits for legitimate later modifications.

## [5] c005 — feat(db): add declarative base, mixins, and session/unit-of-work

- **Commit message:**
  ```
  feat(db): add declarative base, mixins, and session/unit-of-work

  Establishes the persistence foundation every model and repository builds on.

  - app/models/base.py: DeclarativeBase (Base) + IdMixin (surrogate int PK) +
    TimestampMixin (tz-aware created_at/updated_at maintained by the DB via
    server_default/onupdate). One Base.metadata for Alembic to autogenerate from.
  - app/db/session.py: cached engine built from HV_DATABASE_URL (SQLite gets
    check_same_thread=False for Uvicorn's threadpool; pool_pre_ping on), a
    sessionmaker with expire_on_commit=False, a unit_of_work() context manager
    (commit on success / rollback on error / always close), and a get_session()
    FastAPI dependency with the same semantics. Confining engine+session here keeps
    the backend swappable (SQLite<->Postgres) from one place (rule 7.6.2).
  - Package docstrings for models/ and db/.

  Immutability note: clinical append-only records (5.6) keep updated_at for
  forensics; the append-only rule is enforced in the service layer, not by omitting
  columns here.

  Tests (5) against a real temp SQLite DB: mixins populate id+timestamps;
  unit_of_work commits on success and rolls back on error; get_session commits on
  success and rolls back when the consumer raises. Full suite: 25 passed.

  Implements TASKS 0.6 (and part of 0.11).
  Refs: DESIGN 7.2, 7.6, 8, 5.6, 12.2.
  ```
- **Files (in add order):**
  - `backend/app/models/__init__.py`
  - `backend/app/models/base.py`
  - `backend/app/db/__init__.py`
  - `backend/app/db/session.py`
  - `backend/tests/db/__init__.py`
  - `backend/tests/db/test_session.py`
- **Satisfies:** TASKS 0.6, 0.11 (partial) · **Rules:** DESIGN §7.2, §7.6, §8, §5.6, §12.2 · **Phase:** 0
- **Depends on:** [2]
- **Rationale:** Declarative Base + mixins + transactional session — the persistence foundation for all models/repositories.

## [6] c006 — feat(api): add app factory, health probe, and versioned router

- **Commit message:**
  ```
  feat(api): add app factory, health probe, and versioned router

  Makes the backend a runnable ASGI app served by Uvicorn on :8000.

  - app/main.py: create_app() factory building the FastAPI instance, mounting the
    API under /api and disabling /docs+/redoc in production. Exposes a module-level
    `app` for `uvicorn app.main:app`.
  - app/api/router.py: top-level aggregator with a /v1 sub-router, so every route
    lives under /api/v1 and a future v2 slots in without touching v1 (rule 7.6.5).
  - app/api/v1/health.py: GET /api/v1/health liveness/readiness probe that also
    runs a SELECT 1 DB check; a DB failure degrades the `database` field rather
    than 500ing, so callers can tell 'app down' from 'DB unreachable'.
  - Package docstrings for api/ and api/v1/.

  Ordering note: this slice (0.8) is taken before Alembic (0.7) on purpose — it
  gives a runnable app to verify end-to-end now, and Alembic autogenerate is most
  useful once the first real models exist (Phase 1).

  Tests (4): versioned mount, health payload shape + DB=ok, no unversioned /health
  (404), and /docs+/openapi.json served in development. Also verified `app` imports
  via the Uvicorn path. Full suite: 29 passed.

  Implements TASKS 0.8 (and part of 0.11).
  Refs: DESIGN 7.1, 7.6, 8.
  ```
- **Files (in add order):**
  - `backend/app/api/__init__.py`
  - `backend/app/api/v1/__init__.py`
  - `backend/app/api/v1/health.py`
  - `backend/app/api/router.py`
  - `backend/app/main.py`
  - `backend/tests/api/__init__.py`
  - `backend/tests/api/test_health.py`
- **Satisfies:** TASKS 0.8, 0.11 (partial) · **Rules:** DESIGN §7.1, §7.6, §8 · **Phase:** 0
- **Depends on:** [5]
- **Rationale:** Runnable FastAPI app with a versioned router and a DB-aware health probe.

## [7] c007 — feat(api): standardize response envelopes and typed errors

- **Commit message:**
  ```
  feat(api): standardize response envelopes and typed errors

  Adds the shared API contract primitives so every endpoint looks consistent.

  - app/schemas/common.py: ORMModel (from_attributes base for response schemas so
    routers map ORM->schema deliberately, never dumping rows), Page[T] generic
    pagination envelope (items/total/limit/offset with bounds), and ErrorResponse
    (stable machine-readable code + client-safe message + optional details).
  - app/core/errors.py: AppError base + semantic subclasses (NotFound 404,
    ValidationError 422, AuthenticationError 401, PermissionDenied 403,
    Conflict 409). The domain/service layers raise these framework-agnostic
    errors; register_exception_handlers() renders each to its status + the
    ErrorResponse envelope, and maps FastAPI RequestValidationError to the same
    shape. Handlers never leak stack traces (rule 7.6.6).
  - Wired register_exception_handlers into create_app().
  - Package docstring for schemas/.

  Tests (9): Page metadata + bounds validation, ErrorResponse defaults, ORMModel
  hides undeclared fields (no PHI leak), and end-to-end handler mapping for
  404/403/409(subclass code override)/400 plus request-validation 422. Full
  suite: 38 passed.

  Implements TASKS 0.9 (and part of 0.11).
  Refs: DESIGN 7.6 (rules 4,5,6).
  ```
- **Files (in add order):**
  - `backend/app/schemas/__init__.py`
  - `backend/app/schemas/common.py`
  - `backend/app/core/errors.py`
  - `backend/app/main.py`
  - `backend/tests/schemas/__init__.py`
  - `backend/tests/schemas/test_common.py`
  - `backend/tests/core/test_errors.py`
- **Satisfies:** TASKS 0.9, 0.11 (partial) · **Rules:** DESIGN §7.6 (rules 4,5,6) · **Phase:** 0
- **Depends on:** [6]
- **Rationale:** Standard Page[T]/ErrorResponse envelopes + typed domain errors mapped to stable HTTP codes.
- **Note:** `main.py` reappears from c006 (wiring the handlers), permitted by the ledger.

## [8] c008 — feat(repositories): add generic repository base (DAL foundation)

- **Commit message:**
  ```
  feat(repositories): add generic repository base (DAL foundation)

  Adds app.repositories.base.Repository[ModelT] — the generic CRUD foundation
  for the data-access layer, the only layer permitted to query the DB (rule 7.6.2).

  - get/list(limit,offset, ordered by id)/count/add/delete against a caller-
    supplied Session. The session is injected, never created here, so one
    transaction (the unit of work) can span multiple repositories in a use case.
  - add() flushes (not commits) to populate server-generated fields (PK,
    timestamps) immediately while leaving commit/rollback to the unit of work.
  - delete() documents that append-only clinical records (5.6) must not be
    deleted; that rule is enforced in the service layer, while delete() remains
    available for entities where removal is legitimate (e.g. an unbooked slot).
  - Generic over the model so concrete repositories get typed returns and add
    entity-specific queries (docstring shows the get_by_email pattern).
  - Package docstring for repositories/.

  Tests (6) against in-memory SQLite: add flush-populates id+timestamps, get
  hit/miss, paginated ordered list, count, delete, and a subclass query method.
  Full suite: 44 passed.

  Implements TASKS 0.10 (and part of 0.11).
  Refs: DESIGN 7.6 (rule 2), 5.6.
  ```
- **Files (in add order):**
  - `backend/app/repositories/__init__.py`
  - `backend/app/repositories/base.py`
  - `backend/tests/repositories/__init__.py`
  - `backend/tests/repositories/test_base.py`
- **Satisfies:** TASKS 0.10, 0.11 (partial) · **Rules:** DESIGN §7.6 (rule 2), §5.6 · **Phase:** 0
- **Depends on:** [5]
- **Rationale:** Generic Repository[Model] CRUD base confining all DB queries to the DAL.

## [9] c009 — feat(web): bootstrap Jinja2 + HTMX UI with landing page

- **Commit message:**
  ```
  feat(web): bootstrap Jinja2 + HTMX UI with landing page

  Stands up the server-rendered presentation layer (decision 12.1) — one
  process, no Node, no build step.

  - app/web/templates.py: single configured Jinja2Templates instance (autoescape
    on for XSS defense; template dir resolved from __file__).
  - app/web/router.py: thin HTML routes — GET / (landing) and GET /_status (an
    HTMX partial). No business logic / no DB access (rule 7.6.7). Routes are named
    (web-landing, web-status) and excluded from OpenAPI.
  - templates/base.html: layout loading vendored htmx.min.js + app.css via
    url_for('web-static', ...); landing.html: hero + an hx-get button that swaps
    the status partial into #status; partials/status.html: bare fragment.
  - static/app.css: small dependency-free stylesheet; static/htmx.min.js: HTMX
    2.0.3 vendored (no CDN).
  - main.py: mount /static as 'web-static' and include the web router.

  Proves the stack end to end: booted Uvicorn and confirmed GET / (200), the HTMX
  partial swap, htmx.min.js + app.css served, /api/v1/health, and /docs all work in
  a single process on one port.

  Tests (6, tests/web/): landing renders shell with HTMX+CSS, hx-get button wired
  to /_status, status partial is a bare fragment, CSS + HTMX assets served, and web
  routes hidden from OpenAPI. Full suite: 50 passed.

  Implements TASKS 0.12, 0.13 (and part of 0.11).
  Refs: DESIGN 7.3, 7.6 (rule 7), 8, 12.1.
  ```
- **Files (in add order):**
  - `backend/app/web/__init__.py`
  - `backend/app/web/templates.py`
  - `backend/app/web/router.py`
  - `backend/app/web/templates/base.html`
  - `backend/app/web/templates/landing.html`
  - `backend/app/web/templates/partials/status.html`
  - `backend/app/web/static/app.css`
  - `backend/app/web/static/htmx.min.js`
  - `backend/app/main.py`
  - `backend/tests/web/__init__.py`
  - `backend/tests/web/test_landing.py`
- **Satisfies:** TASKS 0.12, 0.13, 0.11 (partial) · **Rules:** DESIGN §7.3, §7.6 (rule 7), §8, §12.1 · **Phase:** 0
- **Depends on:** [6]
- **Rationale:** Server-rendered Jinja2+HTMX bootstrap proving the buildless single-process UI stack.
- **Note:** `main.py` reappears from c006/c007 (mounting static + web router), permitted by the ledger. `htmx.min.js` is a vendored third-party asset (HTMX 2.0.3).

## [10] c010 — feat(db): initialize Alembic with one-command migrate wrappers

- **Commit message:**
  ```
  feat(db): initialize Alembic with one-command migrate wrappers

  Sets up schema migrations (decision 12.5) wired to the app as the single
  source of truth.

  - backend/alembic.ini: script config; DB URL deliberately NOT set here (env.py
    reads HV_DATABASE_URL), UTC timestamped filename template, WARNING logging.
  - backend/alembic/env.py: reads the URL from app Settings and targets
    Base.metadata, with compare_type + compare_server_default and SQLite batch
    mode for safe ALTERs. _import_all_models() hook is in place (empty today) so
    autogenerate 'just works' once Phase 1 adds the first models.
  - backend/alembic/script.py.mako: revision template (modern typing).
  - backend/alembic/versions/.gitkeep: keeps the empty versions dir tracked; the
    first real migration is generated in Phase 1.
  - scripts/migrate.sh + scripts/migrate.ps1: one-command `alembic upgrade head`
    wrappers (resolve repo root, use the venv, run from backend/) so beginners
    never type raw Alembic.

  Verified against a temp SQLite DB: `alembic upgrade head` is a clean no-op with
  no revisions, and `revision --autogenerate` produces a valid script (discarded
  after the smoke test), proving env.py + template + settings-driven URL are wired.
  Full suite: 50 passed.

  Implements TASKS 0.7.
  Refs: DESIGN 8, 12.5.
  ```
- **Files (in add order):**
  - `backend/alembic.ini`
  - `backend/alembic/env.py`
  - `backend/alembic/script.py.mako`
  - `backend/alembic/versions/.gitkeep`
  - `scripts/migrate.sh`
  - `scripts/migrate.ps1`
- **Satisfies:** TASKS 0.7 · **Rules:** DESIGN §8, §12.5 · **Phase:** 0
- **Depends on:** [5]
- **Rationale:** Alembic wired to app settings + Base.metadata, behind one-command migrate wrappers.

## [11] c011 — feat(scripts): add setup/dev/seed/reset-db, Makefile, and README

- **Commit message:**
  ```
  feat(scripts): add setup/dev/seed/reset-db, Makefile, and README

  Completes the no-Docker local-run workflow and closes the Phase 0 exit gate:
  one command per OS boots the whole app (web UI + JSON API) on :8000.

  - scripts/setup.{sh,ps1}: check Python 3.11+, create the venv (idempotent),
    install deps, migrate, then seed.
  - scripts/dev.{sh,ps1}: run the single Uvicorn process with autoreload; PORT is
    overridable.
  - scripts/seed.{sh,ps1}: run app.db.seed (idempotent).
  - scripts/reset-db.{sh,ps1}: drop the SQLite file, re-migrate, re-seed; refuses
    to run against a non-SQLite DATABASE_URL (asks app Settings for the path so
    it honors .env / HV_DATABASE_URL).
  - app/db/seed.py: idempotent seed entrypoint (documented no-op until Phase 1).
  - Makefile: macOS/Linux shortcuts mirroring the scripts (make setup/dev/...).
  - README.md: Python-only prereqs, one-command-per-OS quick start, task table,
    configuration, project layout, and troubleshooting.

  Exit-gate verification (macOS/Linux): ran migrate.sh, seed.sh, reset-db.sh
  successfully, then booted dev.sh and confirmed GET / (200), /api/v1/health
  (status+database ok), and /docs (200) from one process. Full suite: 50 passed.

  Implements TASKS 0.14, 0.15, 0.16, 0.18 and the Phase 0 exit gate.
  Refs: DESIGN 8, 9 (Phase 0).
  ```
- **Files (in add order):**
  - `backend/app/db/seed.py`
  - `scripts/setup.sh`
  - `scripts/dev.sh`
  - `scripts/seed.sh`
  - `scripts/reset-db.sh`
  - `scripts/setup.ps1`
  - `scripts/dev.ps1`
  - `scripts/seed.ps1`
  - `scripts/reset-db.ps1`
  - `Makefile`
  - `README.md`
- **Satisfies:** TASKS 0.14, 0.15, 0.16, 0.18 + Phase 0 exit gate · **Rules:** DESIGN §8, §9 · **Phase:** 0
- **Depends on:** [9, 10]
- **Rationale:** One-command-per-OS setup/dev/seed/reset workflow + README; closes the Phase 0 exit gate.

---

## [12] c012 — feat(models): add User account model and first migration

- **Commit message:**
  ```
  feat(models): add User account model and first migration

  Introduces the base identity every person in the system has (stories A1-A3).

  - app/models/user.py: User(email unique+indexed, password_hash bcrypt-only,
    role, is_active). Role persists by VALUE (patient/nurse/doctor/admin) via a
    non-native Enum so stored data matches JWT/JSON and stays readable in SQL;
    role is indexed for guard/lookup queries. is_active supports soft-deactivation
    (story E1) so audit/history references stay valid instead of hard deletes.
    Role-specific attributes live on separate 1:1 profiles (next slice), keeping
    the account concern clean.
  - alembic/env.py: import app.models.user in _import_all_models() so autogenerate
    sees the table.
  - alembic/versions/20260808_2232_87b91540ffa3_create_users_table.py: first real
    migration. Autogenerated, then REVIEWED per DESIGN 8 (not blindly committed);
    verified it upgrades to the expected schema (unique ix_users_email,
    ix_users_role, all columns/types) and downgrades cleanly on SQLite (batch mode).

  Tests (3): persist + role/defaults, role round-trips as its string value, email
  uniqueness enforced. Full suite: 53 passed.

  Implements TASKS 1.1.
  Refs: DESIGN 4.1, 3 (A1-A3, E1), 8.
  ```
- **Files (in add order):**
  - `backend/app/models/user.py`
  - `backend/alembic/env.py`
  - `backend/alembic/versions/20260808_2232_87b91540ffa3_create_users_table.py`
  - `backend/tests/models/__init__.py`
  - `backend/tests/models/test_user.py`
- **Satisfies:** TASKS 1.1 · **Rules:** DESIGN §4.1, §3 (A1–A3, E1), §8 · **Phase:** 1
- **Depends on:** [3, 5, 10]
- **Rationale:** Base User account (email/hash/role/is_active) + first reviewed Alembic migration.
- **Note:** `alembic/env.py` reappears from c010 (uncommenting the model import), permitted by the ledger.

## [13] c013 — feat(models): add 1:1 role profiles (patient/doctor/nurse)

- **Commit message:**
  ```
  feat(models): add 1:1 role profiles (patient/doctor/nurse)

  Adds the role-specific profile tables, each joined 1:1 to users (DESIGN 4.1).

  - app/models/profile.py: PatientProfile (dob/sex/phone/insurance/emergency
    contact), DoctorProfile (specialty + unique license_no), NurseProfile (ward).
    Each uses user_id as BOTH primary key and FK to users.id (shared-PK 1:1,
    guaranteeing at most one profile per user) with ondelete=CASCADE, and a
    relationship() back to the owning User.
  - Rationale for 1:1 profiles over wide User columns: keeps users focused on
    identity/auth, lets each role's attributes evolve independently, and gives
    clinical FKs a precise target (e.g. slots reference a doctor).
  - alembic/env.py: also import profile in _import_all_models().
  - migration dffddd069d87 (down_revision 87b91540ffa3): creates the three tables.
    Autogenerated, REVIEWED per DESIGN 8; verified the full chain upgrades to head
    producing users + 3 profile tables.

  Tests (5): each profile links + loads its user, professional/ward fields persist,
  shared-PK enforces one-to-one, and duplicate doctor license_no is rejected. Full
  suite: 58 passed.

  Implements TASKS 1.2.
  Refs: DESIGN 4.1, 8.
  ```
- **Files (in add order):**
  - `backend/app/models/profile.py`
  - `backend/alembic/env.py`
  - `backend/alembic/versions/20260808_2234_dffddd069d87_create_role_profile_tables.py`
  - `backend/tests/models/test_profile.py`
- **Satisfies:** TASKS 1.2 · **Rules:** DESIGN §4.1, §8 · **Phase:** 1
- **Depends on:** [12]
- **Rationale:** 1:1 patient/doctor/nurse profiles (shared-PK) extending User with role-specific attributes.
- **Note:** `alembic/env.py` reappears from c010/c012 (adding the profile import), permitted by the ledger.

## [14] c014 — feat(schemas): add auth and user API schemas

- **Commit message:**
  ```
  feat(schemas): add auth and user API schemas

  Defines the API boundary shapes for accounts + auth (stories A1-A4).

  - app/schemas/auth.py: RegisterRequest (EmailStr + min-8 password; no role field
    since only patients self-register, A1), LoginRequest, TokenPair (bearer
    convention for access+refresh, A3/A4), RefreshRequest. MIN_PASSWORD_LENGTH is
    a named constant so the policy is declared once at the boundary.
  - app/schemas/user.py: UserOut (id/email/role/is_active) mapped from ORM via
    ORMModel — deliberately NO password_hash field, so the credential hash can't
    serialize to a client even if a router passes the ORM object (rule 7.6.4);
    UserCreate for admin staff provisioning (explicit role, A2).
  - requirements.txt: pydantic[email] to enable EmailStr validation.

  Tests (6): valid register, short-password + bad-email rejection, empty-password
  rejection, TokenPair bearer default, and UserOut dropping password_hash. Full
  suite: 64 passed.

  Implements TASKS 1.3.
  Refs: DESIGN 3 (A1-A4), 7.6 (rule 4).
  ```
- **Files (in add order):**
  - `backend/app/schemas/auth.py`
  - `backend/app/schemas/user.py`
  - `backend/requirements.txt`
  - `backend/tests/schemas/test_auth.py`
- **Satisfies:** TASKS 1.3 · **Rules:** DESIGN §3 (A1–A4), §7.6 (rule 4) · **Phase:** 1
- **Depends on:** [7, 12]
- **Rationale:** Auth/user Pydantic schemas; UserOut enforces the no-PHI/no-hash serialization boundary.
- **Note:** `requirements.txt` reappears from c001/c004 (adds pydantic[email]), permitted by the ledger.

## [15] c015 — feat(repositories): add UserRepository with email lookups

- **Commit message:**
  ```
  feat(repositories): add UserRepository with email lookups

  Adds app.repositories.user_repository.UserRepository, extending the generic
  Repository with the user-specific queries auth needs: get_by_email (indexed
  single-row login lookup) and email_exists (fail-fast duplicate check for
  registration/provisioning). Keeps all query construction in the DAL (rule 7.6.2)
  so services call methods rather than building queries.

  Groundwork for the register/login slices (TASKS 1.4/1.6); those rows are only
  marked done once the services/endpoints land. No TASKS row fully satisfied here.

  Tests (3): get_by_email hit/miss, email_exists before/after insert, and that
  inherited generic CRUD (get/count) still works. Full suite: 67 passed.

  Refs: DESIGN 7.6 (rule 2), 3 (A1, A3).
  ```
- **Files (in add order):**
  - `backend/app/repositories/user_repository.py`
  - `backend/tests/repositories/test_user_repository.py`
- **Satisfies:** (groundwork for TASKS 1.4, 1.6 — not yet complete) · **Rules:** DESIGN §7.6 (rule 2), §3 · **Phase:** 1
- **Depends on:** [8, 12]
- **Rationale:** User DAL (get_by_email, email_exists) that the register/login services depend on.

## [16] c016 — feat(audit): add AuditLog model and audit service (§5.7)

- **Commit message:**
  ```
  feat(audit): add AuditLog model and audit service (§5.7)

  Adds the mandatory PHI-access audit trail backbone, brought forward before the
  auth service so login/register write audit rows from day one.

  - app/models/audit.py: AuditLog(actor_id?, action, resource_type?, resource_id?,
    patient_id?). actor_id nullable so FAILED LOGINS (no authenticated user) are
    still auditable; patient_id nullable + indexed to enable 'filter by patient'
    (story E2); FKs use ondelete=SET NULL so deleting a user never erases history;
    indexes on actor_id/patient_id/created_at back the admin's audit queries.
    Append-only by policy (service only inserts).
  - app/services/audit_service.py: record_audit(session, *, action, ...) appends
    one row INSIDE the caller's unit of work (keyword-only args; resource_id
    coerced to text). Flushes but never commits, so the audit write is atomic with
    the audited action — no orphan/ missing audit rows.
  - alembic/env.py + migration 9c391aebfa9f (down_revision dffddd069d87): create
    audit_logs + its three indexes. Autogenerated, REVIEWED per DESIGN 8.
  - Adds services/ package docstring.

  Tests (5): model persists with actor+patient, actor_id nullable for failed
  login; service flushes (id available, resource_id text), does NOT commit
  (rollback leaves no row), and is atomic with the caller's commit. Full suite:
  72 passed.

  Implements TASKS 1.10, 1.11.
  Refs: DESIGN 5.7, 4.1, 3 (E2), 8.
  ```
- **Files (in add order):**
  - `backend/app/models/audit.py`
  - `backend/app/services/__init__.py`
  - `backend/app/services/audit_service.py`
  - `backend/alembic/env.py`
  - `backend/alembic/versions/20260808_2239_9c391aebfa9f_create_audit_logs_table.py`
  - `backend/tests/models/test_audit.py`
  - `backend/tests/services/__init__.py`
  - `backend/tests/services/test_audit_service.py`
- **Satisfies:** TASKS 1.10, 1.11 · **Rules:** DESIGN §5.7, §4.1, §3 (E2), §8 · **Phase:** 1
- **Depends on:** [12]
- **Rationale:** Append-only AuditLog + transactional record_audit choke point for the mandatory audit trail.
- **Note:** `alembic/env.py` reappears (adding the audit import), permitted by the ledger.

## [17] c017 — feat(auth): register patient endpoint with audited service

- **Commit message:**
  ```
  feat(auth): register patient endpoint with audited service

  First complete account vertical slice: self-service patient registration
  (story A1), plus the auth service that login/refresh will also use.

  - app/services/auth_service.py: register_patient() creates the User (PATIENT,
    bcrypt-hashed pw) + its 1:1 PatientProfile and audits 'user.register', all in
    the caller's unit of work (atomic). login() verifies credentials and issues an
    access+refresh pair (role rides the access token), auditing 'auth.login' /
    'auth.login_failed'. Security: uniform InvalidCredentials for unknown email,
    wrong password, AND deactivated account, so the API never reveals which emails
    exist. Typed errors EmailAlreadyRegistered(409)/InvalidCredentials(401).
  - app/api/v1/auth.py: POST /api/v1/auth/register -> 201 UserOut (no hash);
    mounted on the v1 router.
  - tests/conftest.py: shared `client` fixture — per-test in-memory SQLite
    (StaticPool) with schema created and get_session overridden (commit/rollback/
    close contract preserved).

  This slice implements register (1.4) and, since login lives in the same service,
  adds+tests login too; the login/refresh ENDPOINTS land in the next slice (1.6/
  1.7), so 1.6/1.7 stay open.

  Tests: service (7) register happy/profile/audit/duplicate + login success-tokens
  /wrong-pw-audited/unknown-email-same-error/deactivated; API (3) 201+safe body,
  409 duplicate, 422 invalid. Full suite: 82 passed.

  Implements TASKS 1.4; completes wiring for 1.11.
  Refs: DESIGN 3 (A1, A3), 5.7, 7.6.
  ```
- **Files (in add order):**
  - `backend/app/services/auth_service.py`
  - `backend/app/api/v1/auth.py`
  - `backend/app/api/router.py`
  - `backend/tests/conftest.py`
  - `backend/tests/services/test_auth_service.py`
  - `backend/tests/api/test_auth.py`
- **Satisfies:** TASKS 1.4, 1.11 · **Rules:** DESIGN §3 (A1, A3), §5.7, §7.6 · **Phase:** 1
- **Depends on:** [14, 15, 16]
- **Rationale:** Audited patient registration endpoint + the auth service (register/login) it builds on.
- **Note:** `api/router.py` reappears from c006 (mounting the auth router), permitted by the ledger.

## [18] c018 — feat(auth): login/refresh/me endpoints and auth dependencies

- **Commit message:**
  ```
  feat(auth): login/refresh/me endpoints and auth dependencies

  Completes the core auth loop (stories A3, A4, A5).

  - app/core/deps.py: get_current_user resolves the caller from a JWT access
    token via EITHER Authorization: Bearer (API/tests) OR the HttpOnly hv_access
    cookie (browser), decoding to the same user so API and web share one auth
    model; rejects missing/invalid tokens and deactivated accounts (401).
    require_roles(*roles) is a dependency factory returning a 403 guard for coarse
    RBAC (A5). Fine-grained ownership checks intentionally stay in services.
  - auth_service.refresh_tokens(): exchanges a valid REFRESH token for a new pair,
    rejecting access-as-refresh and deactivated/unknown subjects, auditing
    auth.refresh / auth.refresh_failed.
  - app/api/v1/auth.py: POST /login, POST /refresh, GET /me (get_current_user).

  Tests: deps (7) header+cookie resolve, missing/invalid/refresh-as-access/
  deactivated -> 401, require_roles allow+deny; service (3) refresh new-pair+audit,
  reject access token, reject deactivated; API (6) login pair, wrong-pw 401, me
  401-unauth + 200-with-bearer, refresh new pair, refresh rejects access token.
  Full suite: 97 passed.

  Implements TASKS 1.6, 1.7, 1.8, 1.9.
  Refs: DESIGN 3 (A3, A4, A5), 7.3, 7.6.
  ```
- **Files (in add order):**
  - `backend/app/core/deps.py`
  - `backend/app/services/auth_service.py`
  - `backend/app/api/v1/auth.py`
  - `backend/tests/core/test_deps.py`
  - `backend/tests/services/test_auth_service.py`
  - `backend/tests/api/test_auth.py`
- **Satisfies:** TASKS 1.6, 1.7, 1.8, 1.9 · **Rules:** DESIGN §3 (A3, A4, A5), §7.3, §7.6 · **Phase:** 1
- **Depends on:** [17]
- **Rationale:** Login/refresh/me endpoints + get_current_user (Bearer/cookie) + require_roles guard.
- **Note:** `auth_service.py`, `api/v1/auth.py`, and the two test files reappear from c017 (adding refresh + endpoints), permitted by the ledger.

## [19] c019 — feat(users): admin-provisioned staff accounts (A2)

- **Commit message:**
  ```
  feat(users): admin-provisioned staff accounts (A2)

  Adds the admin-only staff provisioning path, mirroring real clinics where staff
  accounts are created by an admin, not self-service (story A2).

  - auth_service: extracted _create_account() to centralize the user+matching-
    profile invariant (PatientProfile/DoctorProfile/NurseProfile via a role->profile
    map; ADMIN gets none). register_patient() now delegates to it. Added
    provision_staff(admin_id, UserCreate): rejects the PATIENT role
    (StaffRoleRequired, 409 — patients self-register) and duplicate emails,
    auditing 'user.provision' with the admin as actor.
  - app/api/v1/users.py: POST /api/v1/users gated by require_roles(ADMIN) -> 201
    UserOut; mounted on the v1 router.

  Tests: service (3) provision doctor+profile+audit, reject patient role, reject
  duplicate email; API (4) admin provisions doctor, 401 unauthenticated, 403 for a
  patient caller (RBAC gate), 409 for patient role. Full suite: 104 passed.

  Implements TASKS 1.5.
  Refs: DESIGN 3 (A2, A5), 6, 5.7.
  ```
- **Files (in add order):**
  - `backend/app/services/auth_service.py`
  - `backend/app/api/v1/users.py`
  - `backend/app/api/router.py`
  - `backend/tests/services/test_auth_service.py`
  - `backend/tests/api/test_users.py`
- **Satisfies:** TASKS 1.5 · **Rules:** DESIGN §3 (A2, A5), §6, §5.7 · **Phase:** 1
- **Depends on:** [18]
- **Rationale:** Admin-only staff provisioning (role-appropriate profile + audit), exercising the RBAC guard end to end.
- **Note:** `auth_service.py`, `api/router.py`, and `test_auth_service.py` reappear from earlier slices, permitted by the ledger.

## [20] c020 — feat(db): seed one demo user per role (idempotent)

- **Commit message:**
  ```
  feat(db): seed one demo user per role (idempotent)

  Implements the seed entrypoint so a fresh clone is immediately explorable.

  - app/db/seed.py: seeds one account per role (patient/nurse/doctor/admin) with
    their profiles, all sharing a well-known demo password (Passw0rd!). Idempotent:
    upserts by email so re-running is a no-op; prints how many were created.
    Wrapped in a single unit_of_work().

  Verified end to end: ran scripts/seed.sh against a migrated DB — created 4 users
  first run, 'nothing to do' on the second (idempotent).

  Tests (3): seeds exactly one user per role, second run does not duplicate, and a
  seeded account can authenticate via auth_service.login. Full suite: 107 passed.

  Implements TASKS 1.12.
  Refs: DESIGN 3, 8, 9 (Phase 1).
  ```
- **Files (in add order):**
  - `backend/app/db/seed.py`
  - `backend/tests/db/test_seed.py`
- **Satisfies:** TASKS 1.12 · **Rules:** DESIGN §3, §8 · **Phase:** 1
- **Depends on:** [19]
- **Rationale:** Idempotent demo seed (one user per role) making the app demoable on first run.
- **Note:** `db/seed.py` reappears from c011 (was a no-op placeholder), permitted by the ledger.

## [21] c021 — docs(kb): author Phase 1 knowledge base (auth ADR, access matrix, glossary)

- **Commit message:**
  ```
  docs(kb): author Phase 1 knowledge base (auth ADR, access matrix, glossary)

  Authors the Phase 1 knowledge base — the curated 'why' that is the whole point
  of this project (an AI with this KB should reason correctly where raw source
  wouldn't).

  - knowledge-base/adr/ADR-0003-authentication-and-authorization.md: the auth/RBAC
    decision record — bcrypt (+ why the 4.0.1 pin), JWT access/refresh with type
    enforcement, one identity model over Bearer AND HttpOnly cookie, coarse
    require_roles vs fine service checks, deactivate-not-delete, and the audited
    auth events. Includes consequences + alternatives (server sessions, OAuth,
    argon2).
  - knowledge-base/domain/access-matrix.md: roles x actions with rationale PER
    CELL (why nurses aren't clinical authors, why admin can't author clinical data
    or is the sole audit reader, why doctor needs the fine treating-relationship
    check), phase status per row, and where each enforcement layer lives.
  - knowledge-base/domain/glossary.md: ubiquitous language; nails the
    appointment-vs-encounter distinction and defines later-phase terms now so the
    vocabulary is stable.

  Docs-only slice; full suite remains green (107 passed).

  Implements TASKS 1.14.
  Refs: DESIGN 11, 6, 3, 5.7.
  ```
- **Files (in add order):**
  - `docs/knowledge-base/adr/ADR-0003-authentication-and-authorization.md`
  - `docs/knowledge-base/domain/access-matrix.md`
  - `docs/knowledge-base/domain/glossary.md`
- **Satisfies:** TASKS 1.14 · **Rules:** DESIGN §11, §6, §3, §5.7 · **Phase:** 1
- **Depends on:** [19]
- **Rationale:** Curated Phase 1 KB (auth ADR + access matrix + glossary) — the knowledge-base thesis in practice.

## [22] c022 — test(auth): Phase 1 exit-gate RBAC/audit integration + fix failure-audit rollback

- **Commit message:**
  ```
  test(auth): Phase 1 exit-gate RBAC/audit integration + fix failure-audit rollback

  Adds the Phase 1 exit-gate integration test and fixes a real bug it exposed.

  Bug: failed-login/refresh audit rows were written with flush-only inside the
  request transaction, then the InvalidCredentials raise caused get_session to roll
  back — discarding the very audit row that a failed login must record. The
  service-level test missed it because its fixture didn't roll back on the caught
  exception; the HTTP integration test (real get_session) caught it.

  Fix: record_audit() gains commit=False (default) / commit=True. Failure paths in
  auth_service (auth.login_failed, auth.refresh_failed x2) use commit=True so the
  audit survives the request rollback. commit=True is only used where the audit row
  is the sole pending write, so it can't persist unrelated half-done work. Success
  paths remain flush-only (atomic with the audited action).

  - tests/api/test_rbac_integration.py: exit gate — admin provisions doctor+nurse,
    patient self-registers, all four roles log in + resolve via /me, a patient is
    403 on the admin-only endpoint, and audit rows exist for the key actions; plus
    unknown-email login writes an actor-less auth.login_failed row.
  - tests/services/test_audit_service.py: pins commit=True survives rollback.

  Full suite: 110 passed.

  Implements TASKS 1.13 and the Phase 1 exit gate.
  Refs: DESIGN 9 (Phase 1), 5.7, 6, 3 (A5).
  ```
- **Files (in add order):**
  - `backend/app/services/audit_service.py`
  - `backend/app/services/auth_service.py`
  - `backend/tests/services/test_audit_service.py`
  - `backend/tests/api/test_rbac_integration.py`
- **Satisfies:** TASKS 1.13 + Phase 1 exit gate · **Rules:** DESIGN §9 (Phase 1), §5.7, §6, §3 (A5) · **Phase:** 1
- **Depends on:** [20, 21]
- **Rationale:** Exit-gate integration test; fixes failure-audit loss on request rollback (found by the test).
- **Note:** `audit_service.py`/`auth_service.py`/`test_audit_service.py` reappear from earlier slices (bug fix), permitted by the ledger.

## [23] c023 — feat(models): add AvailabilitySlot model and migration

- **Commit message:**
  ```
  feat(models): add AvailabilitySlot model and migration

  Begins Phase 2 (scheduling) with the bookable-window model (story B1).

  - app/models/scheduling.py: AvailabilitySlot(doctor_id -> users.id CASCADE,
    start_at, end_at, is_booked). Design choices documented: doctor referenced by
    User id (no profile join in scheduling queries); is_booked is a denormalized
    flag kept in lockstep by the booking service in one transaction; slots are
    half-open [start, end) intervals so back-to-back slots don't overlap; composite
    index (doctor_id, start_at) for the 'this doctor's slots by time' query.
  - alembic/env.py + migration ed6325972492 (down_revision 9c391aebfa9f): create
    the table + index. Autogenerated, REVIEWED per DESIGN 8; verified the full
    4-migration chain upgrades to head.

  Tests (2): slot persists with is_booked default False; multiple slots per doctor.
  Full suite: 112 passed.

  Implements TASKS 2.1.
  Refs: DESIGN 4.1, 3 (B1), 5.2, 8.
  ```
- **Files (in add order):**
  - `backend/app/models/scheduling.py`
  - `backend/alembic/env.py`
  - `backend/alembic/versions/20260808_2312_ed6325972492_create_availability_slots_table.py`
  - `backend/tests/models/test_scheduling.py`
- **Satisfies:** TASKS 2.1 · **Rules:** DESIGN §4.1, §3 (B1), §5.2, §8 · **Phase:** 2
- **Depends on:** [12]
- **Rationale:** AvailabilitySlot persistence model (half-open intervals, is_booked flag) + reviewed migration.
- **Note:** `alembic/env.py` reappears (adding the scheduling import), permitted by the ledger.

## [24] c024 — feat(domain): add appointment state machine (§5.1)

- **Commit message:**
  ```
  feat(domain): add appointment state machine (§5.1)

  Adds the pure appointment state machine — the first domain/ module and a piece
  of 'knowledge-base gold' (legal transitions + who may trigger each) that an AI
  can't infer from CRUD code.

  - app/core/exceptions.py (NEW): extracted the AppError hierarchy into a
    framework-free module (plain int status codes, no FastAPI) so the domain can
    raise typed errors while staying pure (rule 7.6.3). Adds IllegalTransition
    (409). core/errors.py now imports+re-exports these and keeps only the HTTP
    handlers, so existing `from app.core.errors import ...` imports still work.
  - app/domain/appointment_state.py: AppointmentStatus + Transition enums and a
    single _TRANSITIONS table (from-states, target, allowed-roles) that IS the
    §5.1 rule. can_transition() (pure predicate) and assert_transition_allowed()
    (returns target state or raises IllegalTransition, distinguishing illegal-
    from-state vs role-not-permitted). Terminal states have no outgoing edges.
  - app/domain/__init__.py package docstring.

  Tests: state machine (9) happy-path lifecycle, illegal-from-state, role-gating
  (patient can't confirm; can cancel, can't check-in; nurse check-in/no-show;
  reschedule->requested; no cancel once in_progress; terminal states inert); plus
  a domain-purity guard test that fails if any domain module imports fastapi/
  sqlalchemy. Full suite: 122 passed.

  Implements TASKS 2.4.
  Refs: DESIGN 5.1, 6, 7.6 (rule 3).
  ```
- **Files (in add order):**
  - `backend/app/core/exceptions.py`
  - `backend/app/core/errors.py`
  - `backend/app/domain/__init__.py`
  - `backend/app/domain/appointment_state.py`
  - `backend/tests/domain/__init__.py`
  - `backend/tests/domain/test_appointment_state.py`
  - `backend/tests/domain/test_domain_purity.py`
- **Satisfies:** TASKS 2.4 · **Rules:** DESIGN §5.1, §6, §7.6 (rule 3) · **Phase:** 2
- **Depends on:** [7]
- **Rationale:** Pure appointment state machine (legal transitions + role gating) with framework-free typed errors.
- **Note:** `core/errors.py` reappears from c007 (refactored to import from the new `core/exceptions.py`), permitted by the ledger.

## [25] c025 — feat(domain): add scheduling rules — conflict/buffer + cancel cutoff (§5.2)

- **Commit message:**
  ```
  feat(domain): add scheduling rules — conflict/buffer + cancel cutoff (§5.2)

  Adds the second pure scheduling domain module.

  - app/domain/scheduling_rules.py: TimeWindow value object (immutable half-open
    [start,end), rejects non-positive duration). windows_overlap() with half-open
    semantics (back-to-back slots don't overlap). conflicts_with_buffer(candidate,
    existing, buffer_minutes): widens each existing window by the buffer on both
    sides before the overlap test, enforcing a minimum gap; buffer=0 reduces to a
    plain overlap check. is_late_cancellation(now, start, cutoff_hours): classifies
    (never blocks) a cancellation as late when the start is within the cutoff or
    already passed. Thresholds are passed in by the caller (from Settings), so the
    domain never reaches into config.

  Tests (11): duration guard, overlap, back-to-back non-overlap, gap-vs-buffer
  both ways, direct overlap with buffer=0, empty existing, all-existing scan, and
  late/not-late/already-started cutoff cases. Full suite: 133 passed.

  Implements TASKS 2.6 (and 2.7's late-cancel classifier).
  Refs: DESIGN 5.2, 7.6 (rule 3).
  ```
- **Files (in add order):**
  - `backend/app/domain/scheduling_rules.py`
  - `backend/tests/domain/test_scheduling_rules.py`
- **Satisfies:** TASKS 2.6 (+ 2.7 classifier) · **Rules:** DESIGN §5.2, §7.6 (rule 3) · **Phase:** 2
- **Depends on:** [24]
- **Rationale:** Pure conflict/buffer + late-cancellation rules over datetimes; thresholds injected from config.

## [26] c026 — feat(models): add Appointment model and migration

- **Commit message:**
  ```
  feat(models): add Appointment model and migration

  Adds the persistence backing the state machine (DESIGN §4.1, §5.1).

  - app/models/scheduling.py: Appointment(patient_id, doctor_id -> users.id
    CASCADE; slot_id -> availability_slots.id RESTRICT, UNIQUE; status; reason;
    cancelled_late). status is the domain AppointmentStatus enum persisted by
    value, so the stored states and the state-machine rules share one source of
    truth; default/server_default = 'requested'. slot_id is unique so a slot backs
    at most one appointment row (double-booking guard at the DB level, complementing
    the domain conflict check). RESTRICT stops deleting a slot out from under an
    appointment. cancelled_late records how a cancel happened (the §5.2 classifier
    decides it); indexes on patient/doctor/status for the common lookups.
  - migration 7c55e96cd3c2 (down_revision ed6325972492): create appointments +
    unique(slot_id) + 3 indexes. Autogenerated, REVIEWED per DESIGN 8; verified the
    5-migration chain upgrades and unique(slot_id) is present.

  Tests (3): status defaults to requested + cancelled_late False, status round-
  trips as its string value, and slot_id uniqueness rejects a second appointment.
  Full suite: 136 passed.

  Implements TASKS 2.3.
  Refs: DESIGN 4.1, 5.1, 5.2, 8.
  ```
- **Files (in add order):**
  - `backend/app/models/scheduling.py`
  - `backend/alembic/versions/20260808_2319_7c55e96cd3c2_create_appointments_table.py`
  - `backend/tests/models/test_scheduling.py`
- **Satisfies:** TASKS 2.3 · **Rules:** DESIGN §4.1, §5.1, §5.2, §8 · **Phase:** 2
- **Depends on:** [23, 24]
- **Rationale:** Appointment model with domain-enum status + unique slot_id (DB double-book guard) + migration.
- **Note:** `scheduling.py` and `test_scheduling.py` reappear from c023 (adding Appointment), permitted by the ledger.

## [27] c027 — feat(appointments): publish/list availability slots (B1) + two fixes

- **Commit message:**
  ```
  feat(appointments): publish/list availability slots (B1) + two fixes

  Doctors can publish availability and everyone can browse open slots.

  - repositories/appointment_repository.py: SlotRepository (list_for_doctor,
    list_open_for_doctor) and AppointmentRepository (list_for_patient/doctor,
    active_windows_for_doctor -> TimeWindow list feeding the pure conflict check;
    excludes cancelled/no-show/completed via _BLOCKING_STATES).
  - services/appointment_service.publish_slot(): validates interval, rejects slots
    conflicting with the doctor's booked appointments within the configured buffer
    (§5.2), audits slot.publish.
  - schemas/appointment.py: SlotCreate (validator: end>start), SlotOut,
    BookingRequest, AppointmentOut.
  - api/v1/appointments.py: POST /slots (doctor-only), GET /slots/mine (doctor),
    GET /slots/open/{doctor_id} (any authed user); mounted on the v1 router.

  Two bugs found by tests and fixed:
    1) core/errors: the request-validation handler passed exc.errors() straight to
       JSONResponse, which crashed when a validator's ctx held a ValueError. Now
       run through jsonable_encoder.
    2) appointment_repository: SQLite drops tzinfo, so DB datetimes came back naive
       and broke naive/aware comparison in the domain. active_windows_for_doctor
       now coerces stored times to UTC-aware (_as_utc) at the DAL boundary.

  Tests: service (4) publish+audit, bad interval, conflict-with-buffer, non-
  conflicting allowed; API (5) publish+list, 422 bad interval, 403 patient, patient
  lists open slots, 401 unauth. Full suite: 145 passed.

  Implements TASKS 2.2 (and 2.5 groundwork: SlotRepository/open-slot listing).
  Refs: DESIGN 3 (B1, B2), 5.2, 7.6.
  ```
- **Files (in add order):**
  - `backend/app/repositories/appointment_repository.py`
  - `backend/app/services/appointment_service.py`
  - `backend/app/schemas/appointment.py`
  - `backend/app/api/v1/appointments.py`
  - `backend/app/api/router.py`
  - `backend/app/core/errors.py`
  - `backend/tests/services/test_appointment_service.py`
  - `backend/tests/api/test_appointments.py`
- **Satisfies:** TASKS 2.2 (+ 2.5 groundwork) · **Rules:** DESIGN §3 (B1, B2), §5.2, §7.6 · **Phase:** 2
- **Depends on:** [25, 26, 18]
- **Rationale:** Doctor slot publishing/listing with buffer-aware conflict check; fixes validation-encoder + naive-datetime bugs.
- **Note:** `api/router.py` and `core/errors.py` reappear from earlier slices, permitted by the ledger.

## [28] c028 — feat(appointments): patient booking flow (B2, B3)

- **Commit message:**
  ```
  feat(appointments): patient booking flow (B2, B3)

  Patients can book an open slot and list their appointments.

  - services/appointment_service.book_appointment(): loads the slot (404 if
    missing), rejects an already-booked slot (SlotConflict 409), re-runs the
    buffer-aware conflict check against the doctor's active appointments (§5.2),
    then marks the slot booked and creates the appointment in 'requested' — all in
    one unit of work so it's atomic. Audits appointment.book. New typed error
    SlotConflict (409).
  - api/v1/appointments.py: POST /appointments (patient-only) and GET
    /appointments/mine.

  Double-booking is guarded three ways: the is_booked flag (fast check), the
  buffer conflict scan, and the unique slot_id constraint on appointments (last-
  line DB guard; the dedicated race test comes in the concurrency slice 2.10).

  Tests: service (3) book marks-slot+audits, unknown slot 404, already-booked 409;
  API (3) patient books + slot leaves open list + shows in mine, second patient on
  same slot 409, doctor booking 403. Full suite: 151 passed.

  Implements TASKS 2.5.
  Refs: DESIGN 3 (B2, B3), 5.2, 7.6.
  ```
- **Files (in add order):**
  - `backend/app/services/appointment_service.py`
  - `backend/app/api/v1/appointments.py`
  - `backend/tests/services/test_appointment_service.py`
  - `backend/tests/api/test_appointments.py`
- **Satisfies:** TASKS 2.5 · **Rules:** DESIGN §3 (B2, B3), §5.2, §7.6 · **Phase:** 2
- **Depends on:** [27]
- **Rationale:** Atomic patient booking (slot load/guard, buffer re-check, mark booked, create appointment, audit).
- **Note:** `appointment_service.py`/`api/v1/appointments.py` and their tests reappear from c027, permitted by the ledger.

## [29] c029 — feat(appointments): state transitions — cancel/late-flag + staff advance (B4, B6)

- **Commit message:**
  ```
  feat(appointments): state transitions — cancel/late-flag + staff advance (B4, B6)

  Wires the pure state machine (§5.1) and late-cancel classifier (§5.2) into a
  service + endpoint.

  - services/appointment_service.change_status(actor, role, appt, transition):
    loads the appointment (404), enforces patient-ownership (403 if a patient
    targets another's appointment — the fine check role alone can't express), then
    delegates legality + role permission to assert_transition_allowed (409 via
    IllegalTransition). Cancelling frees the slot (is_booked=False) and sets
    cancelled_late via is_late_cancellation without blocking (§5.2). Audits
    appointment.<transition>. DB datetimes coerced to UTC-aware before the
    cutoff check.
  - api/v1/appointments.py: POST /appointments/{id}/transitions/{transition};
    any authed user, the state machine decides role permission. Unknown transition
    -> 422 (enum-validated).

  Tests: service (6) confirm+cancel frees slot, not-late vs late cancel, illegal
  transition, patient can't touch others', full staff lifecycle confirm->check_in
  ->begin->complete; API (5) confirm-then-cancel, illegal 409, patient-confirm
  409, unknown-transition 422. Full suite: 161 passed.

  Implements TASKS 2.7, 2.8.
  Refs: DESIGN 5.1, 5.2, 3 (B4, B6), 6, 7.6.
  ```
- **Files (in add order):**
  - `backend/app/services/appointment_service.py`
  - `backend/app/api/v1/appointments.py`
  - `backend/tests/services/test_appointment_service.py`
  - `backend/tests/api/test_appointments.py`
- **Satisfies:** TASKS 2.7, 2.8 · **Rules:** DESIGN §5.1, §5.2, §3 (B4, B6), §6, §7.6 · **Phase:** 2
- **Depends on:** [28]
- **Rationale:** State-machine-driven transitions with cancel slot-freeing + late flag and staff lifecycle advance.
- **Note:** service/router + tests reappear from c027/c028, permitted by the ledger.

## [30] c030 — feat(appointments): staff schedule views + booking race guard test (B5, §5.2)

- **Commit message:**
  ```
  feat(appointments): staff schedule views + booking race guard test (B5, §5.2)

  Adds the staff schedule views and a deterministic concurrency guard test.

  - api/v1/appointments.py: GET /appointments/doctor (doctor's calendar) and GET
    /appointments/ward (nurse-only ward schedule). v1 nurse view is single-ward
    (all appointments); per-ward scoping via NurseProfile.ward is a documented
    future refinement (out of v1). AppointmentRepository.list_all() added.
  - tests/services/test_booking_concurrency.py: simulates the 'last slot' race —
    two independent sessions both insert an appointment for the same slot after
    both passed the is_booked check; the unique(slot_id) constraint lets exactly
    one commit and forces IntegrityError on the other, so no double-book survives.

  Tests: concurrency (1) exactly-one-wins; API (2) doctor calendar lists own,
  ward requires nurse (doctor 403, nurse 200). Full suite: 164 passed.

  Implements TASKS 2.9, 2.10.
  Refs: DESIGN 3 (B5), 5.2, 6, 7.6.
  ```
- **Files (in add order):**
  - `backend/app/repositories/appointment_repository.py`
  - `backend/app/api/v1/appointments.py`
  - `backend/tests/services/test_booking_concurrency.py`
  - `backend/tests/api/test_appointments.py`
- **Satisfies:** TASKS 2.9, 2.10 · **Rules:** DESIGN §3 (B5), §5.2, §6, §7.6 · **Phase:** 2
- **Depends on:** [29]
- **Rationale:** Doctor calendar + nurse ward views and a race test proving unique(slot_id) blocks double-booking.
- **Note:** `appointment_repository.py`/`api/v1/appointments.py`/`test_appointments.py` reappear from earlier slices, permitted by the ledger.

## [31] c031 — feat(web): cookie-session auth and role dashboards

- **Commit message:**
  ```
  feat(web): cookie-session auth and role dashboards

  Builds the server-rendered auth flow so the browser UI has real sessions
  (DESIGN §7.3), the foundation the HTMX booking screens build on.

  - web/deps.py: get_current_web_user (resolves the hv_access cookie to a user or
    None for anonymous nav) and require_web_user (raises _RedirectToLogin for
    protected pages). The internal exception is turned into a 303->/login by a
    handler registered in the app factory, keeping route bodies clean.
  - web/auth.py: GET/POST /login, GET/POST /register (patient self-service), POST
    /logout. Success sets/clears the HttpOnly, SameSite=Lax hv_access cookie;
    failures re-render the form with a generic error + proper status. Calls the
    same auth_service the JSON API uses.
  - web/router.py: GET /dashboard dispatches to a per-role template
    (_DASHBOARD_TEMPLATE).
  - templates: auth/login+register, dashboard/_base + patient/nurse/doctor/admin;
    landing nav links to login/register; app.css gains form + dashboard styles.
  - main.py: mount the web auth router + the redirect handler.

  Verified live (uvicorn + seeded doctor): POST /login -> 303 + cookie; /dashboard
  with cookie renders the doctor view; /dashboard without cookie -> 303 to /login.

  Tests (web, 8): login page renders, anonymous dashboard redirects, register->
  cookie->patient dashboard, bad-login re-render 401, each of doctor/nurse/admin
  lands on its dashboard, logout clears session. Full suite: 172 passed.

  Implements TASKS 2.11 (auth + dashboards portion; HTMX booking screens follow).
  Refs: DESIGN 7.3, 3 (A3, B5), 7.6 (rule 7).
  ```
- **Files (in add order):**
  - `backend/app/web/deps.py`
  - `backend/app/web/auth.py`
  - `backend/app/web/router.py`
  - `backend/app/main.py`
  - `backend/app/web/templates/auth/login.html`
  - `backend/app/web/templates/auth/register.html`
  - `backend/app/web/templates/dashboard/_base.html`
  - `backend/app/web/templates/dashboard/patient.html`
  - `backend/app/web/templates/dashboard/nurse.html`
  - `backend/app/web/templates/dashboard/doctor.html`
  - `backend/app/web/templates/dashboard/admin.html`
  - `backend/app/web/templates/landing.html`
  - `backend/app/web/static/app.css`
  - `backend/tests/web/test_auth_web.py`
- **Satisfies:** TASKS 2.11 (auth + dashboards portion) · **Rules:** DESIGN §7.3, §3 (A3, B5), §7.6 (rule 7) · **Phase:** 2
- **Depends on:** [18, 9]
- **Rationale:** Server-rendered cookie login/register/logout + per-role dashboards; the web auth foundation.
- **Note:** `web/router.py`, `main.py`, `landing.html`, `app.css` reappear from c009, permitted by the ledger.

## [32] c032 — feat(web): HTMX patient booking flow (B2)

- **Commit message:**
  ```
  feat(web): HTMX patient booking flow (B2)

  Completes the Phase 2 web UI with the patient booking screens.

  - repositories/user_repository.list_by_role(role, active_only=True): lists
    active doctors (used to build the booking view; skips deactivated accounts).
  - web/appointments.py: patient-only screens (via _require_patient, 403 for
    staff): GET /appointments/book (doctors + their open slots), POST
    /appointments/book (HTMX — books via appointment_service and swaps in a
    confirmation or inline-error partial), GET /appointments/mine. Thin over the
    same service the JSON API uses (rule 7.6.7).
  - templates/appointments/: book.html (hx-post forms into #book-result),
    partials/book_result.html (confirmation/error fragment), mine.html; patient
    dashboard links re-enabled; app.css slot-list + table styles.
  - main.py mounts the web appointments router.

  Tests (web, 5): book page lists slots, HTMX book returns confirmation partial +
  appears in 'mine', double-book shows error partial (409), page requires login
  (303), doctor is 403 on the patient booking page. Full suite: 177 passed.

  Completes TASKS 2.11.
  Refs: DESIGN 7.3, 3 (B2), 7.6 (rule 7).
  ```
- **Files (in add order):**
  - `backend/app/repositories/user_repository.py`
  - `backend/app/web/appointments.py`
  - `backend/app/main.py`
  - `backend/app/web/templates/dashboard/patient.html`
  - `backend/app/web/templates/appointments/book.html`
  - `backend/app/web/templates/appointments/partials/book_result.html`
  - `backend/app/web/templates/appointments/mine.html`
  - `backend/app/web/static/app.css`
  - `backend/tests/web/test_appointments_web.py`
- **Satisfies:** TASKS 2.11 (complete) · **Rules:** DESIGN §7.3, §3 (B2), §7.6 (rule 7) · **Phase:** 2
- **Depends on:** [31, 28]
- **Rationale:** Patient HTMX booking page + confirmation partial + appointment list; completes the Phase 2 web UI.
- **Note:** `user_repository.py`, `main.py`, `patient.html`, `app.css` reappear from earlier slices, permitted by the ledger.

## [33] c033 — test(appointments): Phase 2 exit-gate scheduling integration

- **Commit message:**
  ```
  test(appointments): Phase 2 exit-gate scheduling integration

  Adds the Phase 2 exit-gate integration test, pinning the full scheduling
  journey end to end over the JSON API.

  - tests/api/test_scheduling_integration.py:
    * test_phase2_exit_gate: doctor publishes a slot, patient books it, a second
      patient is blocked (409 double-book), then staff advance the lifecycle
      confirm(doctor)->check_in(nurse)->begin(doctor)->complete(doctor).
    * test_late_cancellation_is_flagged: a slot 1h out is booked then cancelled;
      cancelled_late is True and the freed slot re-appears in the doctor's open
      slots.

  All green — no product changes needed. Full suite: 179 passed.

  Implements TASKS 2.12 and the Phase 2 exit gate.
  Refs: DESIGN 9 (Phase 2), 5.1, 5.2, 3 (B2-B6).
  ```
- **Files (in add order):**
  - `backend/tests/api/test_scheduling_integration.py`
- **Satisfies:** TASKS 2.12 + Phase 2 exit gate · **Rules:** DESIGN §9 (Phase 2), §5.1, §5.2, §3 · **Phase:** 2
- **Depends on:** [32]
- **Rationale:** End-to-end exit-gate test: book, double-book block, staff lifecycle, late-cancel flag + slot re-open.

## [34] c034 — docs(kb): author Phase 2 knowledge base (business rules #1/#2 + workflows)

- **Commit message:**
  ```
  docs(kb): author Phase 2 knowledge base (business rules #1/#2 + workflows)

  Authors the Phase 2 knowledge base — the curated 'why' behind scheduling.

  - knowledge-base/domain/business-rules.md (NEW): Rule #1 (appointment state
    machine) and Rule #2 (slot conflict/buffer/cancellation cutoff), each with
    statement, why, edge cases (half-open intervals, buffer=0, already-started
    cancel, blocking states, the unique-slot race guard), enforcement locations,
    and the exact tests that pin them. Placeholders for rules #3-#8 with #7 (audit)
    already noted as done.
  - knowledge-base/workflows/appointment-booking.md: Mermaid sequence for
    publish->browse->book with both conflict checks and the error branches.
  - knowledge-base/workflows/appointment-lifecycle.md: Mermaid state diagram +
    cancel sequence (ownership check, slot release, late flag); documents that
    no-show is staff-only and does NOT free the slot (matches _SLOT_FREEING={CANCEL}).

  Docs-only; full suite unchanged at 179 passed.

  Implements TASKS 2.13.
  Refs: DESIGN 11, 5.1, 5.2, 3 (B1-B6).
  ```
- **Files (in add order):**
  - `docs/knowledge-base/domain/business-rules.md`
  - `docs/knowledge-base/workflows/appointment-booking.md`
  - `docs/knowledge-base/workflows/appointment-lifecycle.md`
- **Satisfies:** TASKS 2.13 · **Rules:** DESIGN §11, §5.1, §5.2, §3 · **Phase:** 2
- **Depends on:** [33]
- **Rationale:** Curated Phase 2 KB: business rules #1/#2 with why/edge-cases/tests + booking & lifecycle workflow diagrams.

## [35] c035 — feat(models): add Encounter and Addendum clinical models (§5.6)

- **Commit message:**
  ```
  feat(models): add Encounter and Addendum clinical models (§5.6)

  Begins Phase 3 with the append-only clinical record models.

  - app/models/clinical.py: Encounter(appointment_id UNIQUE -> appointments
    RESTRICT, patient_id, doctor_id, opened_at, closed_at?) — the record of a visit
    that happened, distinct from the appointment (the plan); one encounter per
    appointment. Addendum(target_type, target_id, author_id, note) — an immutable
    correction referencing any clinical record via a lightweight polymorphic
    (type,id) pair, so one table serves every entity. Append-only is enforced in
    the service layer (later slice); the shape here reflects §5.6.
  - alembic/env.py + migration 79326e773cf9 (down_revision 7c55e96cd3c2): create
    encounters + addenda + indexes. Autogenerated, REVIEWED per DESIGN 8; 6-
    migration chain verified.

  Tests (4): encounter persists open, one-encounter-per-appointment uniqueness,
  addendum references its target. Full suite: 182 passed.

  Implements TASKS 3.1 and the Addendum model portion of 3.5.
  Refs: DESIGN 4.1, 5.6, 8.
  ```
- **Files (in add order):**
  - `backend/app/models/clinical.py`
  - `backend/alembic/env.py`
  - `backend/alembic/versions/20260809_0051_79326e773cf9_create_encounters_and_addenda_tables.py`
  - `backend/tests/models/test_clinical.py`
- **Satisfies:** TASKS 3.1 (+ Addendum model of 3.5) · **Rules:** DESIGN §4.1, §5.6, §8 · **Phase:** 3
- **Depends on:** [26]
- **Rationale:** Append-only Encounter + polymorphic Addendum models + migration (persistence for §5.6).
- **Note:** `alembic/env.py` reappears (adding the clinical import), permitted by the ledger.

## [36] c036 — feat(domain): add age-based vitals ranges (§5.5)

- **Commit message:**
  ```
  feat(domain): add age-based vitals ranges (§5.5)

  Adds the pure vitals-flagging rule.

  - app/domain/vitals_ranges.py: VitalsReading value object + flag_out_of_range(
    age_years, reading) returning sorted flags (e.g. heart_rate_high, spo2_low) for
    each recorded value outside its AGE-BANDED normal range. Age bands (infant/
    child/adolescent/adult) capture that the same reading can be normal for one age
    and abnormal for another — the non-obvious §5.5 rule. Only recorded (non-None)
    values are checked. Reference values are illustrative teaching values, not
    medical advice (Non-Goals). Pure module (no framework/DB imports).

  Tests (7): adult all-in-range, adult high HR, SAME HR 150 normal-for-infant vs
  high-for-adult, low/high directions, None ignored, multiple flags sorted, child
  band boundary. Full suite: 189 passed.

  Implements TASKS 3.3.
  Refs: DESIGN 5.5, 7.6 (rule 3).
  ```
- **Files (in add order):**
  - `backend/app/domain/vitals_ranges.py`
  - `backend/tests/domain/test_vitals_ranges.py`
- **Satisfies:** TASKS 3.3 · **Rules:** DESIGN §5.5, §7.6 (rule 3) · **Phase:** 3
- **Depends on:** [24]
- **Rationale:** Pure age-banded vitals range check returning out-of-range flags.

## [37] c037 — feat(domain): add treating-relationship scoping predicate (§5.3)

- **Commit message:**
  ```
  feat(domain): add treating-relationship scoping predicate (§5.3)

  Adds the pure fine-grained access check for reading patient history.

  - app/domain/access_scope.py: can_view_patient_history(viewer_role, viewer_id,
    patient_id, has_treating_relationship). Patient -> own only; Doctor -> only
    with a treating relationship (appointment/encounter) — role alone is not
    enough, which is why this is the fine check behind the coarse role guard;
    Nurse -> may read (supports triage); Admin -> NO clinical read (separation of
    duties). Pure: the relationship fact is supplied by the service from a repo;
    the predicate never touches the DB.

  Tests (4): patient own-only, doctor with/without relationship, nurse allowed,
  admin denied. Full suite: 193 passed.

  Implements TASKS 3.7.
  Refs: DESIGN 5.3, 6, 7.6 (rule 3).
  ```
- **Files (in add order):**
  - `backend/app/domain/access_scope.py`
  - `backend/tests/domain/test_access_scope.py`
- **Satisfies:** TASKS 3.7 · **Rules:** DESIGN §5.3, §6, §7.6 (rule 3) · **Phase:** 3
- **Depends on:** [24]
- **Rationale:** Pure treating-relationship predicate — the fine authorization check role guards can't express.

## [38] c038 — feat(models): add Vitals and Diagnosis clinical models

- **Commit message:**
  ```
  feat(models): add Vitals and Diagnosis clinical models

  Adds the append-only encounter children (stories C1, C2; §5.6).

  - app/models/clinical.py: Vitals(encounter_id, recorded_by, heart_rate/resp_rate
    /systolic_bp/temp_c/spo2 all nullable, flags default '') — the flags column
    snapshots the age-based out-of-range markers (§5.5) computed at record time.
    Diagnosis(encounter_id, author_id, icd_code, description) — doctor-authored,
    append-only; corrections via Addendum.
  - migration 373f7898b52e (down_revision 79326e773cf9): create vitals + diagnoses
    + encounter indexes. Autogenerated, REVIEWED per DESIGN 8; 7-migration chain
    verified.

  Tests (2 added): vitals persist with flags default empty, diagnosis persists.
  Full suite: 195 passed.

  Implements TASKS 3.2, 3.4.
  Refs: DESIGN 4.1, 3 (C1, C2), 5.5, 5.6, 8.
  ```
- **Files (in add order):**
  - `backend/app/models/clinical.py`
  - `backend/alembic/versions/20260809_0058_373f7898b52e_create_vitals_and_diagnoses_tables.py`
  - `backend/tests/models/test_clinical.py`
- **Satisfies:** TASKS 3.2, 3.4 · **Rules:** DESIGN §4.1, §3 (C1, C2), §5.5, §5.6, §8 · **Phase:** 3
- **Depends on:** [35]
- **Rationale:** Vitals (with flags snapshot) + Diagnosis append-only models + migration.
- **Note:** `clinical.py` and `test_clinical.py` reappear from c035, permitted by the ledger.

## [39] c039 — feat(clinical): encounter workflow, vitals, diagnoses, scoped history

- **Commit message:**
  ```
  feat(clinical): encounter workflow, vitals, diagnoses, scoped history

  The Phase 3 clinical use cases, wiring the pure rules (§5.3/§5.5) to
  persistence + audit inside the unit of work; append-only (§5.6) enforced by
  exposing only create/addendum ops (no update/delete).

  - repositories/encounter_repository.py: encounter CRUD-add, per-patient history,
    has_treating_relationship (any shared appointment OR encounter — feeds §5.3),
    and add/list for vitals+diagnoses+addenda.
  - user_repository.get_patient_profile: for age lookup.
  - services/clinical_service.py: open_encounter (idempotent, doctor-owns check),
    record_vitals (computes patient age from profile -> flag_out_of_range,
    stores flags), add_diagnosis (owning-doctor only), add_addendum (clinical staff
    only), get_patient_history (applies can_view_patient_history; audits
    history.read / history.read_denied — denial committed so it survives the 403
    rollback). Every PHI op audited (§5.7).
  - schemas/encounter.py + api/v1/encounters.py: POST /encounters, /{id}/vitals
    (nurse), /{id}/diagnoses (doctor), /addenda, GET /history/{patient_id}; mounted
    on v1 router.

  Tests: service (7) idempotent open, wrong-doctor denied, age-based vitals flag,
  diagnosis owning-doctor, history scoping allow/deny + audit, patient own-only,
  addendum staff-only; API (5) full flow (open->flagged vitals->diagnosis),
  nurse-can't-open 403, doctor-can't-record-vitals 403, history scoping over HTTP,
  patient reads own. Full suite: 207 passed.

  Implements TASKS 3.5, 3.6, 3.8, 3.9, 3.11.
  Refs: DESIGN 3 (C1-C5), 5.3, 5.5, 5.6, 5.7, 7.6.
  ```
- **Files (in add order):**
  - `backend/app/repositories/encounter_repository.py`
  - `backend/app/repositories/user_repository.py`
  - `backend/app/services/clinical_service.py`
  - `backend/app/schemas/encounter.py`
  - `backend/app/api/v1/encounters.py`
  - `backend/app/api/router.py`
  - `backend/tests/services/test_clinical_service.py`
  - `backend/tests/api/test_encounters.py`
- **Satisfies:** TASKS 3.5, 3.6, 3.8, 3.9, 3.11 · **Rules:** DESIGN §3 (C1–C5), §5.3, §5.5, §5.6, §5.7, §7.6 · **Phase:** 3
- **Depends on:** [36, 37, 38]
- **Rationale:** Clinical service+API: encounters, age-flagged vitals, diagnoses, addenda, treating-scoped history, all audited.
- **Note:** `user_repository.py` and `api/router.py` reappear from earlier slices, permitted by the ledger.

## [40] c040 — feat(clinical): consent gating on sensitive encounters (§5.8)

- **Commit message:**
  ```
  feat(clinical): consent gating on sensitive encounters (§5.8)

  Adds the consent gate for sensitive clinical records.

  - models/clinical.Encounter: sensitive + consent_shared boolean flags (default
    False). A sensitive encounter (e.g. mental-health notes) is hidden from
    otherwise-authorized staff unless the patient has shared consent.
  - domain/access_scope.is_encounter_visible(...): pure per-record filter — the
    patient always sees their own; a sensitive record is hidden from staff without
    consent_shared; non-sensitive is normal. Layered ON TOP of
    can_view_patient_history (which gates access to the history at all).
  - clinical_service.get_patient_history: applies the per-record filter after the
    access check.
  - schemas EncounterOut exposes the two flags.
  - migration 69a027b6d00b (down_revision 373f7898b52e): add the two columns. A
    spurious vitals.flags server-default diff was removed during review; 8-chain
    up + downgrade verified.

  Tests: domain (5) patient-own sensitive, staff hidden w/o consent (doctor+nurse),
  staff visible w/ consent, non-sensitive visible; service (1) sensitive filtered
  from treating doctor until consent, patient always sees own. Full suite: 212
  passed.

  Implements TASKS 3.10.
  Refs: DESIGN 5.8, 5.3, 8.
  ```
- **Files (in add order):**
  - `backend/app/models/clinical.py`
  - `backend/app/domain/access_scope.py`
  - `backend/app/services/clinical_service.py`
  - `backend/app/schemas/encounter.py`
  - `backend/alembic/versions/20260809_1608_69a027b6d00b_add_encounter_sensitivity_and_consent_.py`
  - `backend/tests/domain/test_access_scope.py`
  - `backend/tests/services/test_clinical_service.py`
- **Satisfies:** TASKS 3.10 · **Rules:** DESIGN §5.8, §5.3, §8 · **Phase:** 3
- **Depends on:** [39]
- **Rationale:** Consent gate: sensitive encounters hidden from staff without shared consent; patient always sees own.
- **Note:** clinical.py/access_scope.py/clinical_service.py/encounter.py + tests reappear from earlier slices, permitted by the ledger.

## [41] c041 — feat(web): clinical screens — patient history + doctor encounter (C4, C2)

- **Commit message:**
  ```
  feat(web): clinical screens — patient history + doctor encounter (C4, C2)

  Adds the Phase 3 web UI.

  - web/clinical.py: GET /clinical/history (patient's own history, service-scoped;
    renders encounters with vitals + diagnoses), GET /clinical/encounters/{id}
    (owning-doctor only encounter page), POST /clinical/encounters/{id}/diagnoses
    (HTMX — add diagnosis, swap updated list / inline error). Thin over
    clinical_service (rule 7.6.7).
  - templates/encounters/: history.html, detail.html, partials/diagnoses.html;
    patient dashboard gains a 'My medical history' link; app.css clinical styles.
  - main.py mounts the web clinical router.

  Tests (web, 4): patient history page, doctor encounter page + HTMX diagnosis add
  partial, non-owning doctor 403, history requires login (303). Full suite: 216
  passed.

  Implements TASKS 3.12.
  Refs: DESIGN 7.3, 3 (C2, C4), 7.6 (rule 7).
  ```
- **Files (in add order):**
  - `backend/app/web/clinical.py`
  - `backend/app/main.py`
  - `backend/app/web/templates/encounters/history.html`
  - `backend/app/web/templates/encounters/detail.html`
  - `backend/app/web/templates/encounters/partials/diagnoses.html`
  - `backend/app/web/templates/dashboard/patient.html`
  - `backend/app/web/static/app.css`
  - `backend/tests/web/test_clinical_web.py`
- **Satisfies:** TASKS 3.12 · **Rules:** DESIGN §7.3, §3 (C2, C4), §7.6 (rule 7) · **Phase:** 3
- **Depends on:** [39, 31]
- **Rationale:** Web clinical screens: patient history view + doctor encounter page with HTMX diagnosis add.
- **Note:** `main.py`, `patient.html`, `app.css` reappear from earlier slices, permitted by the ledger.

## [42] c042 — test(clinical): Phase 3 exit-gate integration + append-only check

- **Commit message:**
  ```
  test(clinical): Phase 3 exit-gate integration + append-only check

  Adds the Phase 3 exit-gate integration test.

  - tests/api/test_clinical_integration.py:
    * test_phase3_exit_gate: nurse->doctor flow end to end — doctor opens
      encounter, nurse records vitals (HR 60 flagged low for a young child but
      normal for an adult, exercising the age rule), doctor diagnoses, patient
      reads own history, a non-treating doctor is denied; asserts the full set of
      audit actions (encounter.open, vitals.record, diagnosis.create, history.read,
      history.read_denied).
    * test_append_only_no_delete_endpoint: no DELETE/PUT route exists for
      encounters (404/405); corrections go through POST /encounters/addenda —
      proving §5.6 immutability at the API surface.

  All green. Full suite: 218 passed.

  Implements TASKS 3.13 and the Phase 3 exit gate.
  Refs: DESIGN 9 (Phase 3), 5.3, 5.5, 5.6, 5.7.
  ```
- **Files (in add order):**
  - `backend/tests/api/test_clinical_integration.py`
- **Satisfies:** TASKS 3.13 + Phase 3 exit gate · **Rules:** DESIGN §9 (Phase 3), §5.3, §5.5, §5.6, §5.7 · **Phase:** 3
- **Depends on:** [40, 41]
- **Rationale:** Exit-gate: nurse->doctor flow + age-flagged vitals + scoping (allow/deny+audit) + append-only surface.

## [43] c043 — docs(kb): author Phase 3 knowledge base (rules #3/#5/#6/#8 + workflow)

- **Commit message:**
  ```
  docs(kb): author Phase 3 knowledge base (rules #3/#5/#6/#8 + workflow)

  Completes the Phase 3 knowledge base.

  - knowledge-base/domain/business-rules.md: fills in Rule #3 (treating-
    relationship scoping), #5 (age-based vitals ranges), #6 (immutable records/
    addenda), #8 (consent gating) — each with statement, why, edge cases,
    enforcement locations, and the tests that pin it. #7 (audit) already present.
  - knowledge-base/workflows/triage-to-consult.md: Mermaid sequence for the full
    clinical visit (open encounter -> nurse vitals w/ age flags -> doctor diagnosis
    -> scoped history read with the two read gates and audited denial).

  Docs-only; full suite unchanged at 218 passed.

  Implements TASKS 3.14.
  Refs: DESIGN 11, 5.3, 5.5, 5.6, 5.8.
  ```
- **Files (in add order):**
  - `docs/knowledge-base/domain/business-rules.md`
  - `docs/knowledge-base/workflows/triage-to-consult.md`
- **Satisfies:** TASKS 3.14 · **Rules:** DESIGN §11, §5.3, §5.5, §5.6, §5.8 · **Phase:** 3
- **Depends on:** [42]
- **Rationale:** Curated Phase 3 KB: rules #3/#5/#6/#8 with why/edge-cases/tests + triage->consult workflow.

## [44] c044 — feat(models): add prescription domain models (medication/allergy/interaction/rx)

- **Commit message:**
  ```
  feat(models): add prescription domain models (medication/allergy/interaction/rx)

  Begins Phase 4 with the models backing the §5.4 safety checks.

  - app/models/prescription.py: Medication (name unique, drug_class, is_controlled),
    Allergy (patient_id, substance [drug OR class name], reaction, severity),
    DrugInteraction (unordered pair unique + severity), Prescription (encounter_id,
    patient_id, prescriber_id, medication_id RESTRICT, dose, refills, status).
  - Also fixes a recurring autogenerate false-diff at the root: Vitals.flags
    server_default changed from '' to text("''") so it matches SQLite's reflected
    form (the spurious 'changed default' diff appeared on every autogenerate;
    regenerating this migration confirmed it's gone).
  - alembic/env.py + migration f8d94a046c95 (down_revision 69a027b6d00b): create
    the 4 tables + indexes. Autogenerated, REVIEWED per DESIGN 8; 9-migration chain
    verified.

  Tests (5): medication default-not-controlled + unique name, allergy substance,
  interaction pair uniqueness, prescription defaults (refills 0, status active).
  Full suite: 223 passed.

  Implements TASKS 4.1, 4.2, 4.3, 4.4.
  Refs: DESIGN 4.1, 5.4, 8.
  ```
- **Files (in add order):**
  - `backend/app/models/prescription.py`
  - `backend/app/models/clinical.py`
  - `backend/alembic/env.py`
  - `backend/alembic/versions/20260809_1619_f8d94a046c95_create_prescription_domain_tables.py`
  - `backend/tests/models/test_prescription.py`
- **Satisfies:** TASKS 4.1, 4.2, 4.3, 4.4 · **Rules:** DESIGN §4.1, §5.4, §8 · **Phase:** 4
- **Depends on:** [38]
- **Rationale:** Medication/Allergy/DrugInteraction/Prescription models + migration; roots out the vitals.flags false-diff.
- **Note:** `clinical.py` reappears from c035/c038/c040 (flags server_default fix) and `alembic/env.py` from earlier, permitted by the ledger.

## [45] c045 — feat(domain): add prescription safety rules (§5.4)

- **Commit message:**
  ```
  feat(domain): add prescription safety rules (§5.4)

  Adds the pure §5.4 safety-decision logic — the Phase 4 centerpiece.

  - app/domain/prescription_safety.py: DrugFacts + SafetyContext value objects and
    evaluate_prescription(drug, context, *, refills, override_interaction).
    Three checks, in severity order:
      1) allergy (name OR class match) -> HARD BLOCK, non-overridable;
      2) controlled substance -> refills capped at MAX_CONTROLLED_REFILLS (0);
      3) drug interaction -> block with reason 'interaction' UNLESS overridden,
         in which case allowed but the warning is surfaced for the record.
    Allergy is evaluated first so it's always reported and can't be bypassed by an
    override. Pure: the service supplies facts from repos; no I/O here.

  Tests (9): clean allowed, allergy by name/class, allergy non-overridable,
  refill cap over/at limit, interaction block-without/allow-with override,
  allergy-precedes-interaction. Full suite: 232 passed.

  Implements TASKS 4.5, 4.6, 4.7.
  Refs: DESIGN 5.4, 7.6 (rule 3).
  ```
- **Files (in add order):**
  - `backend/app/domain/prescription_safety.py`
  - `backend/tests/domain/test_prescription_safety.py`
- **Satisfies:** TASKS 4.5, 4.6, 4.7 · **Rules:** DESIGN §5.4, §7.6 (rule 3) · **Phase:** 4
- **Depends on:** [24]
- **Rationale:** Pure prescription-safety evaluator: allergy hard-block, refill cap, overridable interaction warn.

## [46] c046 — feat(prescriptions): safety-checked prescribe endpoint + reads (D1, D5)

- **Commit message:**
  ```
  feat(prescriptions): safety-checked prescribe endpoint + reads (D1, D5)

  Wires the §5.4 evaluator to persistence + audit.

  - repositories/prescription_repository.py: MedicationRepository (get_by_name) +
    PrescriptionRepository with the safety-fact queries — allergy_terms_for_patient,
    active_medication_ids_for_patient, interacting_active_medication_ids (candidate's
    interaction partners in either column of the unordered pair, intersected with
    the patient's active meds) — and list_for_patient.
  - services/prescription_service.prescribe(): loads encounter (404) + owning-doctor
    check (403), loads medication (404), gathers facts, runs evaluate_prescription,
    and either audits prescription.blocked (committed, survives raise) + raises
    UnsafePrescription(reason in details) or creates the rx + audits
    prescription.create. list_for_patient for reads.
  - schemas/prescription.py + api/v1/prescriptions.py: POST /prescriptions (doctor,
    safety-checked; override_interaction flag), GET /prescriptions/mine (patient),
    GET /prescriptions/patient/{id} (clinical staff); mounted on v1 router.

  Tests: service (5) clean+audit, allergy block+audit, refill cap, interaction
  block-then-override, wrong-doctor 403; API (5) safe 201, allergy 409(reason),
  refill-cap 409, patient-can't-prescribe 403, patient views own. Full suite: 242
  passed.

  Implements TASKS 4.8, 4.9.
  Refs: DESIGN 3 (D1, D5), 5.4, 5.7, 7.6.
  ```
- **Files (in add order):**
  - `backend/app/repositories/prescription_repository.py`
  - `backend/app/services/prescription_service.py`
  - `backend/app/schemas/prescription.py`
  - `backend/app/api/v1/prescriptions.py`
  - `backend/app/api/router.py`
  - `backend/tests/services/test_prescription_service.py`
  - `backend/tests/api/test_prescriptions.py`
- **Satisfies:** TASKS 4.8, 4.9 · **Rules:** DESIGN §3 (D1, D5), §5.4, §5.7, §7.6 · **Phase:** 4
- **Depends on:** [44, 45, 39]
- **Rationale:** Prescribe service+API enforcing §5.4 (allergy/interaction/refill) with audit; patient/staff reads.
- **Note:** `api/router.py` reappears from earlier slices, permitted by the ledger.

## [47] c047 — feat(db): seed medications and drug interactions

- **Commit message:**
  ```
  feat(db): seed medications and drug interactions

  Extends the idempotent seed with a curated medication catalog + interaction
  pairs so the prescribe flow is demoable on a fresh clone.

  - app/db/seed.py: refactored into _seed_users/_seed_medications/_seed_interactions
    (each idempotent by natural key). Seeds 5 meds (incl. controlled Oxycodone) and
    2 interacting pairs (Warfarin+Aspirin severe, Warfarin+Ibuprofen moderate).
    Uses 2.0 select() style.

  Verified end to end: scripts/seed.sh created 4 users, 5 meds, 2 interactions.

  Tests (2 added): seed creates the expected medication+interaction counts, and
  medication seeding is idempotent. Full suite: 244 passed.

  Implements TASKS 4.10.
  Refs: DESIGN 3, 5.4, 8, 9 (Phase 4).
  ```
- **Files (in add order):**
  - `backend/app/db/seed.py`
  - `backend/tests/db/test_seed.py`
- **Satisfies:** TASKS 4.10 · **Rules:** DESIGN §5.4, §8 · **Phase:** 4
- **Depends on:** [44, 46]
- **Rationale:** Idempotent medication + interaction seed so the safety-checked prescribe flow is demoable.
- **Note:** `db/seed.py` and `test_seed.py` reappear from c020, permitted by the ledger.

## [48] c048 — feat(web): prescribe form on encounter + patient prescriptions list (D1, D5)

- **Commit message:**
  ```
  feat(web): prescribe form on encounter + patient prescriptions list (D1, D5)

  Adds the Phase 4 web UI.

  - web/clinical.py: POST /clinical/encounters/{id}/prescriptions (HTMX — prescribe
    via prescription_service, swap the prescriptions list partial; a §5.4 block
    re-renders the partial with the error + proper status, and an interaction can
    be retried with the override checkbox). GET /clinical/prescriptions (patient's
    own list). encounter detail route now passes medications + prescriptions +
    medications_by_id.
  - templates/prescriptions/: partials/list.html (with inline safety error),
    mine.html; encounter detail gains a Prescriptions section + prescribe form
    (medication select, dose, refills, override-interaction checkbox); patient
    dashboard gains a 'My prescriptions' link; app.css rx styles.

  Tests (web, 3): doctor prescribes via HTMX (partial), allergy block shows error
  partial (409), patient prescriptions page lists the rx. Full suite: 247 passed.

  Implements TASKS 4.11.
  Refs: DESIGN 7.3, 3 (D1, D5), 5.4, 7.6 (rule 7).
  ```
- **Files (in add order):**
  - `backend/app/web/clinical.py`
  - `backend/app/web/templates/encounters/detail.html`
  - `backend/app/web/templates/prescriptions/partials/list.html`
  - `backend/app/web/templates/prescriptions/mine.html`
  - `backend/app/web/templates/dashboard/patient.html`
  - `backend/app/web/static/app.css`
  - `backend/tests/web/test_prescriptions_web.py`
- **Satisfies:** TASKS 4.11 · **Rules:** DESIGN §7.3, §3 (D1, D5), §5.4, §7.6 (rule 7) · **Phase:** 4
- **Depends on:** [46, 41]
- **Rationale:** Web prescribe form (with safety-warning display + override) + patient prescriptions list.
- **Note:** `web/clinical.py`, `encounters/detail.html`, `patient.html`, `app.css` reappear from c041, permitted by the ledger.

## [49] c049 — test(prescriptions): Phase 4 exit-gate safety integration

- **Commit message:**
  ```
  test(prescriptions): Phase 4 exit-gate safety integration

  Adds the Phase 4 exit-gate integration test over the JSON API.

  - tests/api/test_prescription_integration.py:
    * test_phase4_exit_gate: safe rx succeeds; an interaction (Aspirin vs the
      patient's active Warfarin) is blocked 409 with reason 'interaction' and a
      clear message, then proceeds with override_interaction=true; a controlled
      substance (Oxycodone) with refills is capped 409 reason 'refill_cap'.
    * test_allergy_block_is_absolute: an allergy match is refused 409 even with
      override (non-overridable).

  All green — no product changes. Full suite: 249 passed.

  Implements TASKS 4.12 and the Phase 4 exit gate.
  Refs: DESIGN 9 (Phase 4), 5.4.
  ```
- **Files (in add order):**
  - `backend/tests/api/test_prescription_integration.py`
- **Satisfies:** TASKS 4.12 + Phase 4 exit gate · **Rules:** DESIGN §9 (Phase 4), §5.4 · **Phase:** 4
- **Depends on:** [48]
- **Rationale:** Exit-gate: safe rx succeeds; allergy/interaction/refill blocks with clear reasons; override for interactions only.

## [50] c050 — docs(kb): author Phase 4 knowledge base (rule #4 + prescribe workflow)

- **Commit message:**
  ```
  docs(kb): author Phase 4 knowledge base (rule #4 + prescribe workflow)

  Completes the Phase 4 knowledge base.

  - knowledge-base/domain/business-rules.md: adds Rule #4 (prescription safety) —
    the allergy/interaction/refill checks, WHY their severities differ (allergy
    absolute vs interaction overridable vs refill cap), edge cases (allergy checked
    first + name/class match, active-only interactions, blocks audited), enforcement
    locations, and tests.
  - knowledge-base/workflows/prescribe.md: Mermaid sequence for the safety-gated
    prescribe flow with all block branches + the override path.

  Docs-only; full suite unchanged at 249 passed.

  Implements TASKS 4.13.
  Refs: DESIGN 11, 5.4.
  ```
- **Files (in add order):**
  - `docs/knowledge-base/domain/business-rules.md`
  - `docs/knowledge-base/workflows/prescribe.md`
- **Satisfies:** TASKS 4.13 · **Rules:** DESIGN §11, §5.4 · **Phase:** 4
- **Depends on:** [49]
- **Rationale:** Curated Phase 4 KB: rule #4 with severity rationale + prescribe workflow diagram.

## [51] c051 — docs(kb): add ADRs 0001, 0002, 0004, 0005

- **Commit message:**
  ```
  docs(kb): add ADRs 0001, 0002, 0004, 0005

  Begins Phase 5 KB finalization with the remaining architecture decision
  records (ADR-0003 auth was authored in Phase 1).

  - ADR-0001 no-Docker/SQLite: local-first rationale, Postgres opt-in, the SQLite
    caveats + mitigations (batch migrations, tz coercion at the DAL).
  - ADR-0002 append-only clinical records: why edits/deletes are forbidden and
    corrections are addenda (reversing-entry analogy); enforced in the service.
  - ADR-0004 layered architecture: the inward-pointing layers + 7 non-negotiable
    rules, the pure-domain purity test, consequences + alternatives.
  - ADR-0005 audit strategy: service-layer (not middleware), append-only, atomic
    with commit=True on failure paths, nullable actor / SET NULL FKs, admin-only
    reads.

  Docs-only; full suite unchanged at 249 passed.

  Implements TASKS 5.3, 5.4, 5.6, 5.7.
  Refs: DESIGN 11, 1, 5.6, 5.7, 7.2, 7.6, 8.
  ```
- **Files (in add order):**
  - `docs/knowledge-base/adr/ADR-0001-no-docker-sqlite.md`
  - `docs/knowledge-base/adr/ADR-0002-append-only-clinical-records.md`
  - `docs/knowledge-base/adr/ADR-0004-layered-architecture.md`
  - `docs/knowledge-base/adr/ADR-0005-audit-strategy.md`
- **Satisfies:** TASKS 5.3, 5.4, 5.6, 5.7 · **Rules:** DESIGN §11, §1, §5.6, §5.7, §7.2, §7.6, §8 · **Phase:** 5
- **Depends on:** [50]
- **Rationale:** The four remaining ADRs (no-Docker/SQLite, append-only, layering, audit).

## [52] c052 — docs(kb): add ERD, OpenAPI export + contract notes, register workflow, runbook

- **Commit message:**
  ```
  docs(kb): add ERD, OpenAPI export + contract notes, register workflow, runbook

  Continues Phase 5 KB finalization.

  - knowledge-base/api/openapi.json: exported from the app (22 paths); README.md
    adds contract conventions (auth, error envelope + stable codes table,
    pagination, status codes) and the regenerate command.
  - knowledge-base/data/erd.md: Mermaid ERD of all 16 tables + rationale for the
    non-obvious choices (shared-PK profiles, unique slot/appointment links,
    polymorphic addenda, unordered interaction pairs, SET NULL audit FKs).
  - knowledge-base/workflows/register-and-login.md: Mermaid sequence for self-
    registration, admin provisioning, login (uniform failure) + refresh.
  - knowledge-base/runbooks/setup-and-operations.md: setup/seed/reset/test/Postgres,
    migration procedure, and the known gotchas (tz, vitals.flags false-diff,
    bcrypt pin, audit-on-failure).

  Docs-only; full suite unchanged at 249 passed.

  Implements TASKS 5.11, 5.12, 5.14 and completes 5.13 (register diagram).
  Refs: DESIGN 11, 8, 7.6.
  ```
- **Files (in add order):**
  - `docs/knowledge-base/api/openapi.json`
  - `docs/knowledge-base/api/README.md`
  - `docs/knowledge-base/data/erd.md`
  - `docs/knowledge-base/workflows/register-and-login.md`
  - `docs/knowledge-base/runbooks/setup-and-operations.md`
- **Satisfies:** TASKS 5.11, 5.12, 5.13, 5.14 · **Rules:** DESIGN §11, §8, §7.6 · **Phase:** 5
- **Depends on:** [51]
- **Rationale:** ERD + OpenAPI export/notes + register workflow + operations runbook.

## [53] c053 — docs(kb): add KNOWLEDGE-INDEX and AGENTS.md (Phase 5 complete)

- **Commit message:**
  ```
  docs(kb): add KNOWLEDGE-INDEX and AGENTS.md (Phase 5 complete)

  Adds the entry-point map that ties the whole knowledge base together, and the
  agent working guide — completing Phase 5.

  - knowledge-base/KNOWLEDGE-INDEX.md: 'read this first' map — read order, links to
    all 8 business rules, glossary, access matrix, 5 ADRs, ERD, API contract, 5
    workflow diagrams, runbook, and a source map of where behavior lives.
  - AGENTS.md (repo root): golden rules (layering, no ORM serialization, append-
    only, audit, typed errors), the one-commit/ledger working rhythm + DoD,
    commands, the migration procedure, and the gotchas list (tz, server_default
    false-diffs, bcrypt pin, validation encoder, two-transport auth, coarse/fine
    authz).

  Docs-only; full suite unchanged at 249 passed. KB is now complete and cross-
  linked — Phase 5 exit gate met.

  Implements TASKS 5.1, 5.2 and the Phase 5 exit gate.
  Refs: DESIGN 11.
  ```
- **Files (in add order):**
  - `docs/knowledge-base/KNOWLEDGE-INDEX.md`
  - `AGENTS.md`
- **Satisfies:** TASKS 5.1, 5.2 + Phase 5 exit gate · **Rules:** DESIGN §11 · **Phase:** 5
- **Depends on:** [52]
- **Rationale:** KNOWLEDGE-INDEX (the map an AI reads first) + AGENTS.md working guide; closes the Phase 5 exit gate.

## [54] c054 — feat(db): seed a complete clinical journey (demoable on first run)

- **Commit message:**
  ```
  feat(db): seed a complete clinical journey (demoable on first run)

  Begins Phase 6 by enriching the seed so a fresh clone shows a full journey
  without manual setup.

  - app/db/seed.py: _seed_clinical_journey() books a COMPLETED appointment for the
    demo patient with the demo doctor, opens an encounter, records vitals + a J06.9
    diagnosis, and writes one active Amoxicillin prescription. Deterministic base
    time (no wall-clock reads, which the workflow/runtime forbids anyway).
    Idempotent: keyed on the demo patient already having an appointment.

  Verified end to end: scripts/seed.sh creates '1 clinical journey' on first run,
  'nothing to do' on the second.

  Tests (1 added): the journey seeds exactly one appointment/encounter/diagnosis/
  prescription and does not duplicate on re-run. Full suite: 250 passed.

  Implements TASKS 6.2.
  Refs: DESIGN 9 (Phase 6), 3.
  ```
- **Files (in add order):**
  - `backend/app/db/seed.py`
  - `backend/tests/db/test_seed.py`
- **Satisfies:** TASKS 6.2 · **Rules:** DESIGN §9, §3 · **Phase:** 6
- **Depends on:** [47]
- **Rationale:** Idempotent full clinical-journey seed so the app is demoable on first run.
- **Note:** `db/seed.py` and `test_seed.py` reappear from c020/c047, permitted by the ledger.

## [55] c055 — docs(kb): add rule-to-test traceability matrix

- **Commit message:**
  ```
  docs(kb): add rule-to-test traceability matrix

  Adds knowledge-base/domain/traceability.md mapping every DESIGN §5 rule (§5.1-
  §5.8) to its enforcement module and the named tests that pin it, across domain/
  service/api/integration layers, plus the RBAC/access-matrix test coverage.
  Verified the referenced domain test counts by collection (9/11/8/7/9).

  Docs-only; full suite unchanged at 250 passed.

  Implements TASKS 6.1.
  Refs: DESIGN 10, 11, 5.
  ```
- **Files (in add order):**
  - `docs/knowledge-base/domain/traceability.md`
- **Satisfies:** TASKS 6.1 · **Rules:** DESIGN §10, §11, §5 · **Phase:** 6
- **Depends on:** [53]
- **Rationale:** Explicit §5-rule → test traceability matrix across all layers.

## [56] c056 — test(web): cross-cutting web route sweep

- **Commit message:**
  ```
  test(web): cross-cutting web route sweep

  Adds tests/web/test_web_routes_sweep.py — a safety net over the whole server-
  rendered surface (no JS engine needed):
  - public pages (/, /login, /register) render HTML (200);
  - protected pages (/dashboard, /appointments/{book,mine}, /clinical/{history,
    prescriptions}) redirect anonymous visitors to /login (303), parametrized;
  - landing nav shows login/register when logged out; a registered patient reaches
    a dashboard with a logout control;
  - unknown page → 404; static assets (app.css, htmx.min.js) served.

  12 tests added, full suite: 262 passed.

  Implements TASKS 6.3.
  Refs: DESIGN 10, 7.3.
  ```
- **Files (in add order):**
  - `backend/tests/web/test_web_routes_sweep.py`
- **Satisfies:** TASKS 6.3 · **Rules:** DESIGN §10, §7.3 · **Phase:** 6
- **Depends on:** [48]
- **Rationale:** Whole-surface web route sweep: public render, protected redirects, nav state, 404, static.

## [57] c057 — docs: finalize README and rewrite stale PROJECT-BRIEF

- **Commit message:**
  ```
  docs: finalize README and rewrite stale PROJECT-BRIEF

  - README.md: adds the seeded demo-accounts table (all roles, password Passw0rd!),
    a 'what you can do' v1 feature summary (accounts/RBAC, appointments, clinical
    workflow, prescriptions, audit), and a pointer to the knowledge base.
  - PROJECT-BRIEF.md (in ~/shared/webapp/, OUTSIDE the repo root): rewritten from
    the stale pre-pivot finance/inventory draft to describe HealthyVytals — the
    hypothesis, domain, stack, architecture, status, and how to run.

  Docs-only; full suite unchanged at 262 passed.

  Implements TASKS 6.4, 6.5.
  Refs: DESIGN 9 (Phase 6), 11.
  ```
- **Files (in add order):**
  - `README.md`
  - `../PROJECT-BRIEF.md`  *(outside repo_root — see replay note)*
- **Satisfies:** TASKS 6.4, 6.5 · **Rules:** DESIGN §9, §11 · **Phase:** 6
- **Depends on:** [54]
- **Rationale:** Finalized README (demo accounts + feature summary) and rewrote the stale PROJECT-BRIEF.
- **Replay note:** `../PROJECT-BRIEF.md` resolves to `~/shared/webapp/PROJECT-BRIEF.md`, outside the `healthyvytals/` git repo. The replay agent should **skip** it if it is not under version control and commit only `README.md`.

## [58] c058 — fix(seed): use example.com demo emails; final e2e verification

- **Commit message:**
  ```
  fix(seed): use example.com demo emails; final e2e verification

  Final Phase 6 slice: end-to-end verification (6.6), which caught and fixed a
  real bug.

  Bug: seeded demo accounts used @healthyvytals.local, but Pydantic EmailStr
  rejects the reserved .local TLD — so the demo accounts the README told users to
  log in with FAILED at /api/v1/auth/login (422) and on the web login. The seed
  test missed it because it called auth_service.login directly, bypassing the
  EmailStr-validated request schema.

  Fix: switch demo emails to @healthyvytals.example.com (RFC-2606 reserved, made
  for demos) in seed.py, test_seed.py, README.md, the runbook, and PROJECT-BRIEF.

  Verification (6.6): fresh DB -> migrate -> seed -> app; confirmed all four roles
  log in via the API, the seeded journey is visible (doctor calendar shows the
  completed appointment; patient sees 1 prescription + 1 encounter; nurse sees the
  ward), and web landing + /docs serve. Full suite: 262 passed.

  Implements TASKS 6.6 and the project exit gate.
  Refs: DESIGN 9 (Verification), 3 (A3).
  ```
- **Files (in add order):**
  - `backend/app/db/seed.py`
  - `backend/tests/db/test_seed.py`
  - `README.md`
  - `docs/knowledge-base/runbooks/setup-and-operations.md`
  - `../PROJECT-BRIEF.md`  *(outside repo_root — skip on replay if untracked)*
- **Satisfies:** TASKS 6.6 + project exit gate · **Rules:** DESIGN §9 (Verification), §3 · **Phase:** 6
- **Depends on:** [57]
- **Rationale:** Final e2e verification; fixes demo emails that EmailStr rejected (.local) so seeded accounts actually log in.

## [59] c059 — docs: plan v2 scope addendum (feature depth + rich UI, M7–M11)

- **Commit message:**
  ```
  docs: plan v2 scope addendum (feature depth + rich UI, M7-M11)

  Adds the v2 scope plan after review found the web UI too thin: the domain +
  JSON API are complete/tested for all roles, but staff dashboards were
  placeholders and lab/messaging/documents were never in v1.

  - DESIGN.md §13: v2 addendum — confirmed decisions (phased launch, stay local-
    first; vendored Pico.css + role app shell, no build step; multi-milestone),
    milestones M7-M11, the end-to-end cross-role acceptance narrative, and v2
    non-goals.
  - TASKS.md: new phases 7-11 task tables + status-summary rows.

  Methodology unchanged (§9A): one functionality = one ledger slice, tests + KB in
  lockstep. Docs-only; suite unchanged at 262 passed.

  Refs: DESIGN 13, 9A.
  ```
- **Files (in add order):**
  - `docs/DESIGN.md`
  - `docs/TASKS.md`
- **Satisfies:** (v2 planning) · **Rules:** DESIGN §13, §9A · **Phase:** 7
- **Depends on:** [58]
- **Rationale:** v2 plan: DESIGN §13 addendum + TASKS phases 7–11 for feature depth and rich UI.

## [60] c060 — feat(web): app shell with Pico.css + role-aware sidebar (M7.1)

- **Commit message:**
  ```
  feat(web): app shell with Pico.css + role-aware sidebar (M7.1)

  Replaces the minimal hand-rolled styling with a proper app shell (DESIGN §13.1).

  - static/pico.min.css: vendored Pico CSS v2.1.1 (classless framework, one file,
    NO build step — honors §7.3/ADR-0001).
  - base.html: loads Pico + app.css; Pico container header/footer; nav as <ul>.
  - dashboard/_base.html: authenticated app shell — a role-aware sidebar (links
    chosen from a per-role map; every link points at an existing route) + a
    content area with an hgroup header; logout + role badge in the sidebar foot.
  - app.css: rewritten as overrides on Pico — brand teal retint, the .app-shell/
    .app-sidebar layout (responsive: stacks under 768px), role badge, metric-grid
    for dashboard stat tiles, and the small utilities templates still use
    (form-error, status-ok, flag, dash-note, slot-list, inline-check).
  - landing.html: polished hero with Get-started/Log-in buttons; nav as <ul>.

  Existing dashboards/pages render unchanged through the new shell (they only
  override dash_title/dash_content). Verified: Pico linked, shell + sidebar render
  for the doctor role, landing renders. Full suite: 262 passed (38 web).

  Implements TASKS 7.1.
  Refs: DESIGN 13.1, 7.3.
  ```
- **Files (in add order):**
  - `backend/app/web/static/pico.min.css`
  - `backend/app/web/templates/base.html`
  - `backend/app/web/templates/dashboard/_base.html`
  - `backend/app/web/static/app.css`
  - `backend/app/web/templates/landing.html`
- **Satisfies:** TASKS 7.1 · **Rules:** DESIGN §13, §7.3 · **Phase:** 7
- **Depends on:** [59]
- **Rationale:** Vendored Pico.css + role-aware sidebar app shell; the visual foundation for the M7 dashboards.
- **Note:** `base.html`, `_base.html`, `app.css`, `landing.html` reappear from c009/c031, permitted by the ledger. `pico.min.css` is a vendored third-party asset (Pico v2.1.1).

## [61] c061 — feat(web): real doctor worklist dashboard + open-encounter flow (M7.2, M7.3)

- **Commit message:**
  ```
  feat(web): real doctor worklist dashboard + open-encounter flow (M7.2, M7.3)

  Turns the doctor placeholder into a working control center.

  - appointment_repository: scheduled_for_doctor()/scheduled_all() — display joins
    returning view-row dicts (appointment + slot time + patient email, UTC-coerced,
    ordered by start) so the web layer renders without lazy loads.
  - web/router: dashboard route now builds a per-role read-only view model
    (_dashboard_context) — doctor gets appointments/open-count/patient list;
    scaffolding for nurse/admin/patient summaries too.
  - web/clinical: POST /clinical/appointments/{id}/open — doctor action that opens
    (idempotently) the encounter via clinical_service and 303-redirects to it;
    non-doctors 403.
  - dashboard/doctor.html: metric tiles + today's worklist table with an 'Open
    encounter' action per actionable appointment.
  - Aligned all dashboard <title>s to '<Role> — HealthyVytals'; updated the
    role-landing test marker accordingly (title/badge are stable across rebuilds).

  Tests (web, 3): worklist shows the booked patient+reason+action; open-encounter
  redirects to the encounter page (diagnose/prescribe forms present); patient can't
  open. Full suite: 265 passed.

  Implements TASKS 7.2, 7.3.
  Refs: DESIGN 13.2 (M7), 3 (B5, C2, D1), 7.6.
  ```
- **Files (in add order):**
  - `backend/app/repositories/appointment_repository.py`
  - `backend/app/web/router.py`
  - `backend/app/web/clinical.py`
  - `backend/app/web/templates/dashboard/doctor.html`
  - `backend/app/web/templates/dashboard/nurse.html`
  - `backend/app/web/templates/dashboard/admin.html`
  - `backend/app/web/templates/dashboard/patient.html`
  - `backend/tests/web/test_auth_web.py`
  - `backend/tests/web/test_doctor_dashboard_web.py`
- **Satisfies:** TASKS 7.2, 7.3 · **Rules:** DESIGN §13 (M7), §3 (B5, C2, D1), §7.6 · **Phase:** 7
- **Depends on:** [60, 39]
- **Rationale:** Working doctor worklist wired to existing services + open-encounter action into the consult flow.
- **Note:** several web files reappear from earlier slices (dashboards, clinical router, appointment repo), permitted by the ledger.

## [62] c062 — fix(scripts): guard Python version range and rebuild stale venv

- **Commit message:**
  ```
  fix(scripts): guard Python version range and rebuild stale venv

  Hardens setup against the two real setup failures reported from other machines.

  1) Python 3.14 has no prebuilt wheels for pinned deps (pydantic-core), so pip
     fell back to a Rust build that crashes. setup.sh/.ps1 now check BOTH bounds
     (3.11 <= X < 3.14); if $PYTHON is unset, setup.sh auto-tries python3.13/3.12/
     3.11/python3/python and picks the first supported one, else prints a clear
     'install 3.11-3.13' message instead of a cryptic maturin error.
  2) A .venv copied from another machine/OS can't execute ('cannot execute binary
     file'). Both scripts now detect an unusable .venv and recreate it.

  Also echoes the chosen interpreter/version. Verified: 3.13 accepted, 3.14
  rejected, and a fresh setup.sh run rebuilds+migrates+seeds cleanly. Docs/tests
  unaffected; full suite: 265 passed.

  Refs: DESIGN 8, ADR-0001.
  ```
- **Files (in add order):**
  - `scripts/setup.sh`
  - `scripts/setup.ps1`
  - `README.md`
  - `docs/knowledge-base/runbooks/setup-and-operations.md`
- **Satisfies:** (setup hardening) · **Rules:** DESIGN §8 · **Phase:** 7
- **Depends on:** [11]
- **Rationale:** Setup version guard (3.11–3.13) + stale-venv rebuild; turns two cryptic cross-machine failures into clear guidance.
- **Note:** `scripts/setup.{sh,ps1}` reappear from c011, permitted by the ledger.

## [63] c063 — feat(web): nurse ward board + triage vitals-entry UI (M7.4, M7.5)

- **Commit message:**
  ```
  feat(web): nurse ward board + triage vitals-entry UI (M7.4, M7.5)

  Turns the nurse placeholder into a working ward board and brings the vitals
  flow (previously API-only) to the browser.

  - clinical_service: extracted _ensure_encounter(appointment, actor) — creates the
    encounter attributed to the appointment's assigned doctor regardless of who
    triggers it, so a nurse can bring it into being during triage. open_encounter
    keeps its doctor-ownership check and delegates to it. New
    record_vitals_for_appointment(nurse, appointment, reading) ensures the encounter
    then records vitals (reusing the age-flagging + audit path).
  - web/clinical: nurse routes — POST /appointments/{id}/check-in (state machine),
    GET/POST /appointments/{id}/vitals (form + HTMX submit → flagged result
    partial). All nurse-gated.
  - dashboard/nurse.html: ward board with metrics, check-in + record-vitals actions;
    encounters/vitals_form.html + partials/vitals_result.html.

  Tests: web (4) board lists appt+actions, check-in 303, nurse records vitals
  (HTMX, flagged, persisted), patient 403; service (1) triage creates the encounter
  (attributed to the doctor) + flags. Full suite: 270 passed.

  Implements TASKS 7.4, 7.5.
  Refs: DESIGN 13.2 (M7), 3 (B5, B6, C1), 5.5, 7.6.
  ```
- **Files (in add order):**
  - `backend/app/services/clinical_service.py`
  - `backend/app/web/clinical.py`
  - `backend/app/web/templates/dashboard/nurse.html`
  - `backend/app/web/templates/encounters/vitals_form.html`
  - `backend/app/web/templates/encounters/partials/vitals_result.html`
  - `backend/tests/web/test_nurse_dashboard_web.py`
  - `backend/tests/services/test_clinical_service.py`
- **Satisfies:** TASKS 7.4, 7.5 · **Rules:** DESIGN §13 (M7), §3 (B5, B6, C1), §5.5, §7.6 · **Phase:** 7
- **Depends on:** [61, 39]
- **Rationale:** Nurse ward board (check-in) + browser vitals-entry with age-flagging; encounter auto-created at triage.
- **Note:** `clinical_service.py`, `web/clinical.py`, `nurse.html`, `test_clinical_service.py` reappear from earlier slices, permitted by the ledger.

## [64] c064 — feat(web): admin console — user management + audit-log viewer (M7.6, M7.7)

- **Commit message:**
  ```
  feat(web): admin console — user management + audit-log viewer (M7.6, M7.7)

  Turns the admin placeholder into a real operations console (stories E1-E3).

  - auth_service: list_all_users() and set_user_active(admin, user, is_active) —
    soft activate/deactivate (never delete) with audit (user.activate/deactivate);
    refuses self-deactivation (no lock-out); NotFound on unknown user.
  - audit_service.list_audit(actor/patient/action filters, newest first) — the
    read side of the append-only trail (admin-only via the route).
  - web/admin.py: /admin/users (list + provision form + activate/deactivate) and
    /admin/audit (filterable viewer), all _require_admin (403 otherwise). main.py
    mounts it; admin sidebar gains Users + Audit log links.
  - templates: dashboard/admin.html (role-count metrics + quick links),
    admin/users.html, admin/audit.html.

  Tests: web (5) dashboard counts+links, provision via console, deactivate→login
  401 + reactivate, non-admin 403 on both pages, audit lists+filters; service (2)
  set_user_active toggles+audits, admin-cannot-deactivate-self. Full suite: 277
  passed.

  Implements TASKS 7.6, 7.7.
  Refs: DESIGN 13.2 (M7), 3 (E1-E3), 5.7, 6, 7.6.
  ```
- **Files (in add order):**
  - `backend/app/services/auth_service.py`
  - `backend/app/services/audit_service.py`
  - `backend/app/web/admin.py`
  - `backend/app/main.py`
  - `backend/app/web/templates/dashboard/_base.html`
  - `backend/app/web/templates/dashboard/admin.html`
  - `backend/app/web/templates/admin/users.html`
  - `backend/app/web/templates/admin/audit.html`
  - `backend/tests/web/test_admin_web.py`
  - `backend/tests/services/test_auth_service.py`
- **Satisfies:** TASKS 7.6, 7.7 · **Rules:** DESIGN §13 (M7), §3 (E1–E3), §5.7, §6, §7.6 · **Phase:** 7
- **Depends on:** [63, 19, 16]
- **Rationale:** Admin user console (provision + activate/deactivate) and filterable audit-log viewer, admin-gated + audited.
- **Note:** `auth_service.py`, `audit_service.py`, `main.py`, `_base.html`, `admin.html`, `test_auth_service.py` reappear from earlier slices, permitted by the ledger.

## [65] c065 — feat(web): patient overview home + route sweep + web-UI KB (M7 complete)

- **Commit message:**
  ```
  feat(web): patient overview home + route sweep + web-UI KB (M7 complete)

  Finishes M7 (real role dashboards).

  - dashboard/patient.html: overview home — upcoming-appt / active-rx / total
    metric tiles + quick-action buttons (book, appointments, history, prescriptions).
  - tests/web/test_web_routes_sweep.py: adds /admin/users + /admin/audit to the
    protected-redirect sweep; asserts the patient overview content renders.
  - knowledge-base/web-ui-map.md (+ KNOWLEDGE-INDEX link): documents every role's
    screens, the app shell, HTMX conventions, and where each route lives.

  Milestone check (live, seeded): all four roles log in to a real dashboard
  (app-shell + metric tiles), no placeholders. Full suite: 279 passed.

  Implements TASKS 7.8, 7.9, 7.10 and the M7 exit gate.
  Refs: DESIGN 13.2 (M7), 7.3, 11.
  ```
- **Files (in add order):**
  - `backend/app/web/templates/dashboard/patient.html`
  - `backend/tests/web/test_web_routes_sweep.py`
  - `docs/knowledge-base/web-ui-map.md`
  - `docs/knowledge-base/KNOWLEDGE-INDEX.md`
- **Satisfies:** TASKS 7.8, 7.9, 7.10 + M7 exit gate · **Rules:** DESIGN §13 (M7), §7.3, §11 · **Phase:** 7
- **Depends on:** [64]
- **Rationale:** Patient overview home + expanded route sweep + web-UI map; closes the M7 exit gate.
- **Note:** `patient.html`, `test_web_routes_sweep.py`, `KNOWLEDGE-INDEX.md` reappear from earlier slices, permitted by the ledger.

## [66] c066 — feat(models): add LabOrder and LabResult models + migration (M8.1)

- **Commit message:**
  ```
  feat(models): add LabOrder and LabResult models + migration (M8.1)

  Begins M8 (lab results & reports) with the new domain's persistence.

  - app/models/lab.py: LabOrder(encounter_id, patient_id, ordered_by, test_code,
    test_name, notes?, status default 'ordered') and LabResult(lab_order_id,
    recorded_by, analyte, value, unit?, reference_low/high?, abnormal). Append-only
    like other clinical records (§5.6): an order has a lifecycle string but is never
    deleted; results are immutable once recorded. A panel accumulates multiple
    result rows. abnormal + reference range are stored so the flag is explainable.
  - alembic/env.py: register the lab module.
  - migration 5f45e83bfad3 (down_revision f8d94a046c95): create both tables +
    indexes. Autogenerated, REVIEWED per DESIGN 8 (removed a redundant duplicate
    index during review); verified the 10-migration chain upgrades and downgrades
    cleanly.

  Tests (2): order defaults to 'ordered'; an order accumulates results with mixed
  abnormal flags. Full suite: 281 passed.

  Implements TASKS 8.1.
  Refs: DESIGN 13.2 (M8), 4.1, 5.6, 8.
  ```
- **Files (in add order):**
  - `backend/app/models/lab.py`
  - `backend/alembic/env.py`
  - `backend/alembic/versions/20260818_0809_5f45e83bfad3_create_lab_orders_and_lab_results_tables.py`
  - `backend/tests/models/test_lab.py`
- **Satisfies:** TASKS 8.1 · **Rules:** DESIGN §13 (M8), §4.1, §5.6, §8 · **Phase:** 8
- **Depends on:** [35]
- **Rationale:** LabOrder + LabResult append-only models + reviewed migration; the M8 persistence foundation.
- **Note:** `alembic/env.py` reappears (registering the lab module), permitted by the ledger.

## [67] c067 — feat(domain): add lab abnormal-flagging rule (M8.2)

- **Commit message:**
  ```
  feat(domain): add lab abnormal-flagging rule (M8.2)

  Adds the pure lab-result flagging rule.

  - app/domain/lab_rules.py: is_abnormal(value, reference_low, reference_high) —
    True when the value is outside the inclusive [low, high] range. Either bound may
    be None (open-ended); both None → always normal. Pure (no framework/DB), so it
    is unit-testable and the domain-purity guard covers it.

  Tests (7): within/below/above, inclusive bounds, open-ended low + high, no-range.
  Purity guard still green.

  Implements TASKS 8.2 (flagging portion; visibility scoping reuses §5.3/§5.8 in
  the service slice).
  Refs: DESIGN 13.2 (M8), 7.6 (rule 3).
  ```
- **Files (in add order):**
  - `backend/app/domain/lab_rules.py`
  - `backend/tests/domain/test_lab_rules.py`
- **Satisfies:** TASKS 8.2 · **Rules:** DESIGN §13 (M8), §7.6 (rule 3) · **Phase:** 8
- **Depends on:** [66]
- **Rationale:** Pure lab abnormal-flagging (value vs reference range); visibility scoping reuses §5.3/§5.8 in the service.

## [68] c068 — feat(labs): order/record/view lab service + API (M8.3, M8.4)

- **Commit message:**
  ```
  feat(labs): order/record/view lab service + API (M8.3, M8.4)

  Wires the lab domain to persistence + audit and exposes it over the API.

  - repositories/lab_repository.py: LabOrderRepository (list_for_patient/encounter,
    pending) + LabResultRepository (list_for_order).
  - services/lab_service.py: order_lab (doctor owns the encounter), record_result
    (clinical staff only; flags abnormal via domain/lab_rules, appends result, moves
    order → resulted), get_patient_labs (reuses treating-relationship scoping §5.3;
    audits lab.read / lab.read_denied). All audited; append-only.
  - schemas/lab.py + api/v1/labs.py: POST /labs/orders (doctor), POST
    /labs/orders/{id}/results (nurse/doctor), GET /labs/patient/{id} (scoped);
    mounted on the v1 router.

  Tests: service (5) owning-doctor order, abnormal-flag + resulted, normal not
  flagged, patient-can't-record, scoping allow/deny+audit; API (3) full flow
  (order→abnormal result→patient views resulted), patient-can't-order 403,
  non-treating-doctor 403. Full suite: 296 passed.

  Implements TASKS 8.3, 8.4.
  Refs: DESIGN 13.2 (M8), 5.3, 5.6, 5.7, 7.6.
  ```
- **Files (in add order):**
  - `backend/app/repositories/lab_repository.py`
  - `backend/app/services/lab_service.py`
  - `backend/app/schemas/lab.py`
  - `backend/app/api/v1/labs.py`
  - `backend/app/api/router.py`
  - `backend/tests/services/test_lab_service.py`
  - `backend/tests/api/test_labs.py`
- **Satisfies:** TASKS 8.3, 8.4 · **Rules:** DESIGN §13 (M8), §5.3, §5.6, §5.7, §7.6 · **Phase:** 8
- **Depends on:** [67, 39]
- **Rationale:** Lab service+API: order (doctor)/record (staff, flagged)/view (scoped), all audited & append-only.
- **Note:** `api/router.py` reappears from earlier slices, permitted by the ledger.

## [69] c069 — feat(web): lab UI — order/review, nurse queue, patient results (M8.5)

- **Commit message:**
  ```
  feat(web): lab UI — order/review, nurse queue, patient results (M8.5)

  Brings the lab flow to the browser across all three roles.

  - web/clinical.py: doctor POST /encounters/{id}/labs (order → HTMX lab list),
    patient GET /clinical/labs (own results), nurse GET /clinical/labs/queue
    (pending orders) + POST /clinical/labs/{id}/results (record → HTMX result list).
    encounter-detail context gains lab orders (_lab_rows_for_encounter).
  - templates/labs/: mine.html, queue.html, partials/order_list.html +
    result_list.html (abnormal flagged); encounter/detail.html gains a Labs section
    (list + order form); sidebar adds patient 'Lab results' + nurse 'Lab queue';
    patient dashboard gains a Lab results quick action.

  Tests: web (4) doctor orders via encounter (partial), nurse queue+record abnormal,
  patient views own labs, non-nurse queue 403; route sweep adds /clinical/labs.
  Full suite: 301 passed.

  Implements TASKS 8.5.
  Refs: DESIGN 13.2 (M8), 7.3, 7.6 (rule 7).
  ```
- **Files (in add order):**
  - `backend/app/web/clinical.py`
  - `backend/app/web/templates/labs/mine.html`
  - `backend/app/web/templates/labs/queue.html`
  - `backend/app/web/templates/labs/partials/order_list.html`
  - `backend/app/web/templates/labs/partials/result_list.html`
  - `backend/app/web/templates/encounters/detail.html`
  - `backend/app/web/templates/dashboard/_base.html`
  - `backend/app/web/templates/dashboard/patient.html`
  - `backend/tests/web/test_labs_web.py`
  - `backend/tests/web/test_web_routes_sweep.py`
- **Satisfies:** TASKS 8.5 · **Rules:** DESIGN §13 (M8), §7.3, §7.6 (rule 7) · **Phase:** 8
- **Depends on:** [68, 65]
- **Rationale:** Lab web UI across roles: doctor order/review, nurse queue+record, patient results (HTMX).
- **Note:** `web/clinical.py`, `encounters/detail.html`, `_base.html`, `patient.html`, `test_web_routes_sweep.py` reappear from earlier slices, permitted by the ledger.

## [70] c070 — test+docs(labs): M8 exit-gate integration + KB rule #9 & workflow

- **Commit message:**
  ```
  test+docs(labs): M8 exit-gate integration + KB rule #9 & workflow

  Closes M8 (lab results & reports).

  - tests/api/test_lab_integration.py: the M8 acceptance narrative end to end —
    doctor orders → nurse records an abnormal result → patient AND treating doctor
    both see the resulted order → non-treating doctor 403; asserts the full audit
    set (lab.order/result/read/read_denied).
  - knowledge-base/domain/business-rules.md: Rule #9 (lab flagging + visibility) —
    statement, why (separates order/record/view roles), edge cases, enforcement,
    tests.
  - knowledge-base/workflows/lab-order-to-result.md: Mermaid cross-role sequence;
    linked from KNOWLEDGE-INDEX.

  All green. Full suite: 302 passed.

  Implements TASKS 8.6 and the M8 exit gate.
  Refs: DESIGN 13.2 (M8), 11, 5.3.
  ```
- **Files (in add order):**
  - `backend/tests/api/test_lab_integration.py`
  - `docs/knowledge-base/domain/business-rules.md`
  - `docs/knowledge-base/workflows/lab-order-to-result.md`
  - `docs/knowledge-base/KNOWLEDGE-INDEX.md`
- **Satisfies:** TASKS 8.6 + M8 exit gate · **Rules:** DESIGN §13 (M8), §11, §5.3 · **Phase:** 8
- **Depends on:** [69]
- **Rationale:** M8 exit-gate cross-role integration test + KB rule #9 and lab workflow diagram.

## [71] c071 — feat(messaging): M9 patient↔care-team messaging + in-app notifications

- **Commit message:**
  ```
  feat(messaging): M9 patient↔care-team messaging + in-app notifications

  Adds v2 M9: patient ↔ care-team messaging and in-app notifications, as one
  end-to-end vertical slice across every layer (DESIGN §13).

  - models/messaging.py: MessageThread (unique per patient+staff pair) + Message
    (append-only, §5.6). models/notification.py: Notification (derived read-model,
    mark-read allowed).
  - alembic 90dfe13e2800: create message_threads, messages, notifications
    (reviewed; upgrade+downgrade verified on temp SQLite). Registered in env.py.
  - domain/messaging_rules.can_staff_message_patient: pure care-team scope,
    mirroring §5.3 (doctor needs treating relationship; nurse may; admin never).
  - repositories/messaging_repository.py + notification_repository.py: DAL only.
  - services/messaging_service.py: send (find-or-create thread, notify recipient,
    audit message.send), list_threads, get_thread (participant-only; audits
    message.read / message.read_denied). services/notification_service.py: the
    single notify() choke point + list/unread_count/mark_read/mark_all_read.
  - Event emission wired into appointment_service (booked/status-change),
    lab_service (resulted), prescription_service (created).
  - api/v1/messages.py: threads, thread detail, send, notifications feed,
    mark-read, read-all. schemas/messaging.py. Registered in api/router.py.
  - web/messaging.py + templates (inbox, thread, notification feed + HTMX
    partials); sidebar links for patient/doctor/nurse; app.css chat/feed styles.
  - KB: business-rules Rule #10, workflows/messaging-and-notifications.md,
    KNOWLEDGE-INDEX updated.

  All green. Full suite: 320 passed.

  Implements TASKS 9.1–9.5 and the M9 exit gate.
  Refs: DESIGN §13 (M9), §5.3, §5.6, §5.7.
  ```
- **Files (in add order):**
  - `backend/app/models/messaging.py`
  - `backend/app/models/notification.py`
  - `backend/alembic/versions/20260905_1614_90dfe13e2800_create_messaging_and_notification_tables.py`
  - `backend/alembic/env.py`
  - `backend/app/domain/messaging_rules.py`
  - `backend/app/repositories/messaging_repository.py`
  - `backend/app/repositories/notification_repository.py`
  - `backend/app/services/messaging_service.py`
  - `backend/app/services/notification_service.py`
  - `backend/app/services/appointment_service.py`
  - `backend/app/services/lab_service.py`
  - `backend/app/services/prescription_service.py`
  - `backend/app/schemas/messaging.py`
  - `backend/app/api/v1/messages.py`
  - `backend/app/api/router.py`
  - `backend/app/web/messaging.py`
  - `backend/app/main.py`
  - `backend/app/web/templates/messages/inbox.html`
  - `backend/app/web/templates/messages/thread.html`
  - `backend/app/web/templates/messages/partials/thread_list.html`
  - `backend/app/web/templates/messages/partials/message_list.html`
  - `backend/app/web/templates/notifications/feed.html`
  - `backend/app/web/templates/notifications/partials/feed_list.html`
  - `backend/app/web/templates/dashboard/_base.html`
  - `backend/app/web/static/app.css`
  - `backend/tests/domain/test_messaging_rules.py`
  - `backend/tests/services/test_messaging_service.py`
  - `backend/tests/services/test_notification_service.py`
  - `backend/tests/api/test_messages.py`
  - `backend/tests/web/test_messaging_web.py`
  - `docs/knowledge-base/domain/business-rules.md`
  - `docs/knowledge-base/workflows/messaging-and-notifications.md`
  - `docs/knowledge-base/KNOWLEDGE-INDEX.md`
  - `docs/TASKS.md`
  - `README.md`
- **Satisfies:** TASKS 9.1–9.5 + M9 exit gate · **Rules:** DESIGN §13 (M9), §5.3, §5.6, §5.7 · **Phase:** 9
- **Depends on:** [70]
- **Rationale:** M9 messaging & notifications end-to-end: care-team-scoped threads, event-driven in-app notifications, KB Rule #10 + workflow diagram.

## [72] c072 — feat(llm): add LLM component layer (stub-default, opt-in real providers)

- **Commit message:**
  ```
  feat(llm): add LLM component layer (stub-default, opt-in real providers)

  Introduces core/llm: the app's first AI infrastructure, treating an LLM as a
  system component rather than a chatbot (DESIGN §14, ADR-0006). This is the
  worked example behind the companion book's Chapter 2.

  - core/llm/client.py: LLMClient wrapping a raw call in the five disciplines —
    output contracts (validated AssistantSchema), reliability (retry w/ exponential
    backoff + jitter, transparent fallback model, per-request timeout), determinism
    (input-hash cache → effective determinism), routing (triage/reasoning tiers),
    observability (a CallRecord per call). Exhausted-chain errors preserve the
    specific failure type (e.g. SchemaValidationError).
  - core/llm/providers.py: Provider protocol + ProviderResult. StubProvider is the
    DEFAULT — deterministic, offline, no SDK; resolves $ref/$defs enums so structured
    responses validate. AnthropicProvider/OpenAIProvider are opt-in with lazily
    imported SDKs and an actionable error when the package is missing.
  - core/llm/errors.py: typed LLMError family (extends AppError → central HTTP map);
    ProviderError carries `retryable`; distinct SchemaValidationError and LLMRefusal.
  - core/llm/observability.py: CallRecord (model/tokens/latency/stop_reason/cache_hit/
    fallback_used/attempts) logged to 'healthyvytals.llm'; CallStats aggregate. Kept
    separate from the compliance audit trail (ADR-0005).
  - core/llm/schemas.py: AssistantSchema base (json_schema_for_prompt + validation).
  - core/config.py: HV_LLM_* settings (provider, api key, tier→model routing, fallback,
    timeout, retries, cache) + model_for_tier(); .env.example documents them.
  - tests/core/llm/test_llm_client.py: 15 offline tests across all five disciplines
    (fake provider + stub; sleep stubbed so backoff is instant).

  Default provider is the offline stub, so the app boots and the full suite runs with
  no API key and no vendor SDK (ADR-0006, mirrors ADR-0001's SQLite default).
  Full suite: 335 passed.

  Implements TASKS 12.1–12.2. Refs: DESIGN §14, ADR-0006.
  ```
- **Files (in add order):**
  - `backend/app/core/llm/__init__.py`
  - `backend/app/core/llm/errors.py`
  - `backend/app/core/llm/observability.py`
  - `backend/app/core/llm/schemas.py`
  - `backend/app/core/llm/providers.py`
  - `backend/app/core/llm/client.py`
  - `backend/app/core/config.py`
  - `.env.example`
  - `backend/tests/core/llm/__init__.py`
  - `backend/tests/core/llm/test_llm_client.py`
- **Satisfies:** TASKS 12.1–12.2 · **Rules:** DESIGN §14, ADR-0006 · **Phase:** 12
- **Depends on:** [71]
- **Rationale:** LLM component layer: contracts+reliability+determinism+routing+observability, stub-default/opt-in real providers (ADR-0006).

## [73] c073 — feat(vitals): add rule-grounded AI vitals triage assistant

- **Commit message:**
  ```
  feat(vitals): add rule-grounded AI vitals triage assistant

  Adds the app's first AI-assisted use case on top of core/llm (DESIGN §14, M12,
  Rule #11): a vitals triage assistant that produces a structured, advisory
  VitalsAssessment to help staff prioritize recorded vitals.

  - core/llm/vitals_schema.py: VitalsAssessment output contract (summary, urgency
    enum, red_flags, recommended_action, confidence).
  - services/vitals_assistant_service.py: composes the PURE domain rule
    vitals_ranges.flag_out_of_range (Rule #5, ground truth) with the LLM, which only
    explains/prioritizes the flags. Safety clamp: a flagged reading can never be
    'routine'. Safe degradation: on LLM refusal/error, returns a rules-only
    assessment instead of failing. Audited via record_audit (Rule #7) as
    llm.vitals_assessed / llm.vitals_assessed_degraded.
  - tests/services/test_vitals_assistant_service.py: 6 offline tests (ground-truth
    wins, degradation, urgency clamp, audit rows).
  - KB in lockstep: business-rules Rule #11, ADR-0006, workflows/vitals-assistant.md,
    KNOWLEDGE-INDEX; DESIGN §14; TASKS Phase 12; README AI section.

  Decision-support, human-in-the-loop — never diagnosis (Non-Goals). Runs offline via
  the stub provider. Full suite: 341 passed.

  Implements TASKS 12.3–12.5 and the M12 exit gate. Refs: DESIGN §14, §5.5, §5.7, ADR-0006.
  ```
- **Files (in add order):**
  - `backend/app/core/llm/vitals_schema.py`
  - `backend/app/services/vitals_assistant_service.py`
  - `backend/tests/services/test_vitals_assistant_service.py`
  - `docs/DESIGN.md`
  - `docs/knowledge-base/adr/ADR-0006-llm-component-layer.md`
  - `docs/knowledge-base/domain/business-rules.md`
  - `docs/knowledge-base/workflows/vitals-assistant.md`
  - `docs/knowledge-base/KNOWLEDGE-INDEX.md`
  - `docs/TASKS.md`
  - `README.md`
- **Satisfies:** TASKS 12.3–12.5 + M12 exit gate · **Rules:** DESIGN §14, §5.5, §5.7, ADR-0006 · **Phase:** 12
- **Depends on:** [72]
- **Rationale:** AI vitals assistant: rule-grounded (Rule #5 is source of truth), human-in-the-loop, safe degradation, audited; KB Rule #11 + workflow.

## [74] c074 — feat(vitals): expose AI vitals assistant via API + nurse web UI

- **Commit message:**
  ```
  feat(vitals): expose AI vitals assistant via API + nurse web UI

  Makes the M12 vitals assistant reachable by users, not just callable in code
  (DESIGN §14.5a, Rule #11 exposure). Real backend models work automatically when
  HV_LLM_PROVIDER + HV_LLM_API_KEY are set; the offline stub serves it otherwise.

  - services/vitals_assistant_service.assess_encounter_vitals: resolves an encounter's
    patient age + latest recorded reading, enforces the §5.3 treating-relationship rule
    for doctors (audited llm.vitals_assessed_denied on refusal), then delegates to
    assess_vitals. Nurses are permitted triage-wide.
  - schemas/encounter.VitalsAssessmentOut: wire model mirroring the LLM output contract
    (the contract is not leaked directly to clients).
  - api/v1/encounters.py: POST /{id}/vitals-assessment (coarse nurse/doctor role gate).
  - web/clinical.py: POST /clinical/appointments/{id}/vitals-assessment renders an HTMX
    partial; vitals_result.html gains a 'Get AI triage assist' button + target; new
    partial vitals_assessment.html with urgency badge + 'advisory, not a diagnosis'
    disclaimer; urgency-badge CSS in app.css.
  - tests: api/test_vitals_assessment.py (5 — role gate, treating-relationship deny,
    vitals-first precondition) + web/test_vitals_assistant_web.py (3).
  - KB in lockstep: Rule #11 (exposure + tests), workflows/vitals-assistant.md entry
    points, DESIGN §14.5a, TASKS 12.6–12.8, README.

  Runs offline via the stub; full suite: 349 passed.

  Implements TASKS 12.6–12.8 and the M12 exposure gate. Refs: DESIGN §14, §5.3, §5.7.
  ```
- **Files (in add order):**
  - `backend/app/services/vitals_assistant_service.py`
  - `backend/app/schemas/encounter.py`
  - `backend/app/api/v1/encounters.py`
  - `backend/app/web/clinical.py`
  - `backend/app/web/templates/encounters/partials/vitals_result.html`
  - `backend/app/web/templates/encounters/partials/vitals_assessment.html`
  - `backend/app/web/static/app.css`
  - `backend/tests/api/test_vitals_assessment.py`
  - `backend/tests/web/test_vitals_assistant_web.py`
  - `docs/DESIGN.md`
  - `docs/knowledge-base/domain/business-rules.md`
  - `docs/knowledge-base/workflows/vitals-assistant.md`
  - `docs/TASKS.md`
  - `README.md`
- **Satisfies:** TASKS 12.6–12.8 + M12 exposure gate · **Rules:** DESIGN §14, §5.3, §5.7 · **Phase:** 12
- **Depends on:** [73]
- **Rationale:** Expose the vitals assistant to users: API endpoint + nurse HTMX panel, §5.3 authz, real-model-when-keyed; docs/ledger in lockstep.

## [75] c075 — feat(vitals): vitals trend charts on history (Chart.js, scoped read)

- **Commit message:**
  ```
  feat(vitals): vitals trend charts on history (Chart.js, scoped read)

  Plots a patient's vitals over time on the medical-history page (DESIGN §15.1, M13,
  completes M10.4; Rule #12, ADR-0007).

  - repositories/encounter_repository.vitals_for_patient: join vitals via the owning
    encounter, oldest-first.
  - services/clinical_service.get_vitals_series: same authorization + consent gate as
    reading history (can_view_patient_history + is_encounter_visible), audited
    vitals_series.read / read_denied.
  - api/v1/patients.py: GET /patients/{id}/vitals-series -> VitalsSeriesOut; registered
    in api/router. schemas/encounter: VitalsPoint + VitalsSeriesOut.
  - Vendored Chart.js UMD (app/web/static/chart.umd.min.js) — one static file, no build
    (ADR-0007). base.html gains a head_extra block; history.html renders a canvas + init
    script (progressive enhancement: raw vitals stay listed if JS/fetch fails or <2 pts).
  - app.css: chart-frame styles. KB: Rule #12, ADR-0007, workflows/vitals-trends.md,
    KNOWLEDGE-INDEX; DESIGN §15.1; TASKS 10.4/13.1-13.2.
  - tests: api/test_vitals_series.py (4), web/test_vitals_trends_web.py (1).

  Runs offline; full suite green. Refs: DESIGN §15, §5.3, §5.8, ADR-0007.
  ```
- **Files (in add order):**
  - `backend/app/repositories/encounter_repository.py`
  - `backend/app/services/clinical_service.py`
  - `backend/app/schemas/encounter.py`
  - `backend/app/api/v1/patients.py`
  - `backend/app/api/router.py`
  - `backend/app/web/static/chart.umd.min.js`
  - `backend/app/web/templates/base.html`
  - `backend/app/web/templates/encounters/history.html`
  - `backend/app/web/static/app.css`
  - `backend/tests/api/test_vitals_series.py`
  - `backend/tests/web/test_vitals_trends_web.py`
  - `docs/knowledge-base/adr/ADR-0007-client-charting-vendored-chartjs.md`
  - `docs/knowledge-base/domain/business-rules.md`
  - `docs/knowledge-base/workflows/vitals-trends.md`
  - `docs/knowledge-base/KNOWLEDGE-INDEX.md`
  - `docs/DESIGN.md`
  - `docs/TASKS.md`
  - `README.md`
- **Satisfies:** TASKS 10.4, 13.1–13.2 · **Rules:** DESIGN §15, §5.3, §5.8, ADR-0007 · **Phase:** 13
- **Depends on:** [74]
- **Rationale:** Vitals trend charts: scoped series endpoint + vendored Chart.js on history page.

## [76] c076 — feat(appointments): show times/doctor + patient cancel on My Appointments

- **Commit message:**
  ```
  feat(appointments): show times/doctor + patient cancel on My Appointments

  Improves the existing Phase-2 booking flow (DESIGN §15.2, M13) without rebuilding the
  service.

  - repositories/appointment_repository: scheduled_for_patient + _scheduled now aliases
    User twice (patient + doctor email) and carries cancelled_late.
  - web/appointments.py: my_appointments uses the display join; new POST /{id}/cancel
    delegates to appointment_service.change_status(CANCEL) (ownership + state machine +
    slot freeing + late flag + audit already enforced there) and re-renders the list.
  - templates: mine.html + new partials/appointment_list.html (time, doctor, status pill,
    HTMX cancel with confirm); polished book.html (grouped slots, formatted times).
  - app.css: status pills, btn-sm, empty-state.
  - tests: 2 new in web/test_appointments_web.py (time+doctor+cancel shown; cancel flow).

  Full suite green. Refs: DESIGN §15, §5.1, §5.2.
  ```
- **Files (in add order):**
  - `backend/app/repositories/appointment_repository.py`
  - `backend/app/web/appointments.py`
  - `backend/app/web/templates/appointments/mine.html`
  - `backend/app/web/templates/appointments/partials/appointment_list.html`
  - `backend/app/web/templates/appointments/book.html`
  - `backend/app/web/static/app.css`
  - `backend/tests/web/test_appointments_web.py`
  - `docs/DESIGN.md`
  - `docs/TASKS.md`
  - `README.md`
- **Satisfies:** TASKS 13.3 · **Rules:** DESIGN §15, §5.1, §5.2 · **Phase:** 13
- **Depends on:** [75]
- **Rationale:** Booking UX: My Appointments shows time/doctor/status + in-place cancel; polished book page.

## [77] c077 — style(ui): cohesive visual refresh within the Pico shell (M13)

- **Commit message:**
  ```
  style(ui): cohesive visual refresh within the Pico shell (M13)

  A visual refresh (DESIGN §15.3, M13), pure CSS + template tweaks, no build step
  (ADR-0001 intact).

  - app.css: richer teal token ramp, elevation/shadow scale, larger radius, gradient
    hero, card polish, refined sidebar, active-nav styling, and dark-mode parity. Every
    pre-existing selector preserved.
  - dashboard/_base.html: sidebar marks the current section aria-current=page (url_for
    cast to str; matches by exact/prefix path).
  - DESIGN §15.3; README v2 note.

  Route-sweep + full suite green (356). Refs: DESIGN §15, ADR-0001.
  ```
- **Files (in add order):**
  - `backend/app/web/static/app.css`
  - `backend/app/web/templates/dashboard/_base.html`
  - `docs/DESIGN.md`
  - `README.md`
- **Satisfies:** TASKS 13.4 · **Rules:** DESIGN §15, ADR-0001 · **Phase:** 13
- **Depends on:** [76]
- **Rationale:** Visual refresh: design tokens, elevation, active-nav, status pills, dark-mode — no build step.
