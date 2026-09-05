# HealthyVytals — Knowledge Base Index

> **Read this first.** This is the map an AI (or engineer) should read before
> changing HealthyVytals. The whole point of the project is that this curated
> knowledge base lets you reason about the system end-to-end — the *why* behind
> the code, not just the *what*. Pair it with the source under `backend/app/`.

## Read order
1. **This index** — the map.
2. **[AGENTS.md](AGENTS.md)** — conventions, layering rules, and gotchas that will
   bite you if you skip them.
3. **[../DESIGN.md](../DESIGN.md)** — the authoritative spec (problem, domain,
   rules §5, architecture §7, methodology §9A).
4. **[../TASKS.md](../TASKS.md)** — what's built vs. remaining, per slice.
5. The domain + ADR pages below, as relevant to your change.

## Domain rules (the "gold" — an AI can't infer these from code)
- **[domain/business-rules.md](domain/business-rules.md)** — all 8 rules with
  statement, *why*, edge cases, enforcement location, and the tests that pin them:
  #1 appointment state machine (§5.1) · #2 slot conflict/buffer/cutoff (§5.2) ·
  #3 treating-relationship scoping (§5.3) · #4 prescription safety (§5.4) ·
  #5 age-based vitals ranges (§5.5) · #6 append-only records (§5.6) ·
  #7 mandatory audit (§5.7) · #8 consent gating (§5.8) ·
  #9 lab flagging & visibility (§13, M8) ·
  #10 care-team messaging & notifications (§13, M9) ·
  #11 AI vitals assistant — rule-grounded, human-in-the-loop (§14, M12) ·
  #12 vitals-trends read scoping (§15, M13).
- **[domain/glossary.md](domain/glossary.md)** — ubiquitous language (note the
  appointment-vs-encounter distinction).
- **[domain/access-matrix.md](domain/access-matrix.md)** — roles × actions with
  rationale per cell; where each enforcement layer lives.

## Architecture decisions (ADRs)
- [ADR-0001](adr/ADR-0001-no-docker-sqlite.md) — no Docker, SQLite default
- [ADR-0002](adr/ADR-0002-append-only-clinical-records.md) — append-only records
- [ADR-0003](adr/ADR-0003-authentication-and-authorization.md) — JWT + bcrypt, RBAC
- [ADR-0004](adr/ADR-0004-layered-architecture.md) — layered, pure domain
- [ADR-0005](adr/ADR-0005-audit-strategy.md) — audit strategy
- [ADR-0006](adr/ADR-0006-llm-component-layer.md) — LLM as a system component (stub-default, opt-in real)
- [ADR-0007](adr/ADR-0007-client-charting-vendored-chartjs.md) — client charting via vendored Chart.js (no build step)

## Data & API
- **[data/erd.md](data/erd.md)** — entity-relationship diagram + rationale (16 tables).
- **[api/README.md](api/README.md)** + [api/openapi.json](api/openapi.json) —
  API conventions, stable error codes, and the exported contract.

## Workflows (Mermaid sequence/state diagrams)
- [register-and-login](workflows/register-and-login.md) (A1–A4)
- [appointment-booking](workflows/appointment-booking.md) (B1–B3)
- [appointment-lifecycle](workflows/appointment-lifecycle.md) — cancel/no-show (B4, B6)
- [triage-to-consult](workflows/triage-to-consult.md) (C1–C5)
- [prescribe](workflows/prescribe.md) — with safety checks (D1–D5)
- [lab-order-to-result](workflows/lab-order-to-result.md) — labs, cross-role (v2 M8)
- [messaging-and-notifications](workflows/messaging-and-notifications.md) — care-team messaging + event notifications (v2 M9)
- [vitals-assistant](workflows/vitals-assistant.md) — AI vitals triage assistant, rule-grounded + human-in-the-loop (v2 M12)
- [vitals-trends](workflows/vitals-trends.md) — vitals trend charts (Chart.js, scoped like history) (v2 M13)

## Web UI
- **[web-ui-map.md](web-ui-map.md)** — the server-rendered role screens (patient/
  nurse/doctor/admin), the app shell, HTMX conventions, and where each route lives.

## Operations
- **[runbooks/setup-and-operations.md](runbooks/setup-and-operations.md)** — setup,
  seed, reset, migrations, Postgres, and known gotchas.

## Where behavior lives (source map)
```
backend/app/
  core/        config, security (JWT/bcrypt), roles, deps (get_current_user,
               require_roles), errors + exceptions, audit context
  core/llm/    LLM component layer (ADR-0006): LLMClient (contracts, reliability,
               determinism, routing, observability), providers (stub-default/opt-in),
               output-contract schemas ← the book's Chapter 2 example
  domain/      PURE rules: appointment_state, scheduling_rules, vitals_ranges,
               access_scope, prescription_safety   ← the KB's business-rules map here
  services/    use cases: auth, appointment, clinical, prescription, audit
  repositories/ the ONLY layer that queries the DB
  models/      SQLAlchemy entities (see ERD)
  api/v1/      JSON endpoints (versioned)
  web/         server-rendered Jinja2 + HTMX UI (same services as the API)
  db/          engine/session/unit-of-work, seed
```

## Deferred-commit ledger
Git isn't initialized; every change is journaled to
[../COMMIT_LEDGER.md](../COMMIT_LEDGER.md) / `../commits/ledger.json` (one entry =
one functionality). See [../commits/README.md](../commits/README.md) for the
replay procedure.
