# ADR-0003 — Authentication (JWT + bcrypt) and Authorization (RBAC)

- **Status:** Accepted
- **Date:** 2026-08-08
- **Phase:** 1 (Accounts & RBAC)
- **Related:** [access-matrix.md](../domain/access-matrix.md), [glossary.md](../domain/glossary.md),
  DESIGN §3 (stories A1–A5, E1–E3), §6 (access matrix), §7.6 (layering).

## Context

HealthyVytals must authenticate four kinds of users (patient, nurse, doctor,
admin) and authorize their actions against protected health information (PHI).
The app is local-first and buildless (no Node, one process), and it is accessed
two ways that must share one identity model:

1. the **JSON API** (`/api/v1/...`), used by tests and any programmatic client;
2. the **server-rendered web UI** (Jinja2 + HTMX), used by a browser.

We need an approach that (a) works for both surfaces, (b) keeps credentials safe,
and (c) makes authorization decisions explicit and testable.

## Decision

### Passwords — bcrypt via passlib
Passwords are stored only as **bcrypt** hashes (`app/core/security.py`,
`hash_password`/`verify_password`). bcrypt embeds its salt and cost factor in the
hash string, so there is no separate salt column and the parameters travel with
the hash. Verification is constant-time and returns `False` (never raises) on a
malformed stored hash. We pin `bcrypt~=4.0.1` because passlib 1.7.4 reads
`bcrypt.__about__.__version__`, which bcrypt 4.1 removed.

### Sessions — JWT access + refresh tokens
Auth uses two **JWTs** carrying a `type` claim:

- **access** — short-lived (default 30 min), sent on every request; carries the
  user id (`sub`) and `role` so guards can authorize without a DB round-trip.
- **refresh** — long-lived (default 7 days), used only to mint new access tokens;
  carries **no** role/authorization claims.

`decode_token(token, expected_type=...)` enforces signature, expiry, **and** the
token type, so an access token can never be replayed where a refresh token is
required, or vice versa (story A4).

### Two transports, one identity
`get_current_user` (`app/core/deps.py`) accepts the access token from **either**
an `Authorization: Bearer` header (API/tests) **or** an HttpOnly `hv_access`
cookie (browser). Both decode to the same `User`, so the API and the web UI share
one auth model (DESIGN §7.3). An HttpOnly cookie is used for the browser so the
token is not readable by JavaScript (XSS token-theft defense) and needs no JS to
attach.

### Authorization — coarse RBAC + fine service checks
Two layers (DESIGN §6):

- **Coarse** — `require_roles(*roles)` is a dependency factory returning a guard
  that admits only the listed roles and raises **403** otherwise (story A5). Role
  groupings (`app/core/roles.py`) encode least-privilege decisions:
  `CLINICAL_AUTHORS = {doctor}`, `AUDIT_READERS = {admin}`, etc.
- **Fine** — ownership and treating-relationship checks (§5.3) require domain data
  and live in the **service layer**, never in `roles.py` or routers.

### Account lifecycle
- **Patients self-register** (`POST /api/v1/auth/register`, story A1).
- **Staff are admin-provisioned** (`POST /api/v1/users`, admin-only, story A2):
  patients cannot be created this way; staff cannot self-register.
- Accounts are **deactivated, not deleted** (`is_active`, story E1). A deactivated
  user fails both login and `get_current_user`, so a still-valid token stops
  working the moment the account is disabled. Deactivation preserves audit/history
  references.

### Auditing
Every auth outcome writes an append-only `AuditLog` row (§5.7): `user.register`,
`user.provision`, `auth.login`, `auth.login_failed`, `auth.refresh`,
`auth.refresh_failed`. Failed logins are audited even though there is no
authenticated actor (nullable `actor_id`).

## Consequences

**Positive**
- One identity model serves both API and web UI.
- Stateless access tokens mean no server-side session store.
- Token-type enforcement closes the access-as-refresh replay hole.
- Uniform `InvalidCredentials` on unknown-email / wrong-password / deactivated
  means the API does not reveal which emails are registered.
- Role on the access token avoids a DB lookup on every authorized request.

**Negative / trade-offs**
- Stateless tokens cannot be revoked before expiry; we mitigate with short access
  lifetimes and the `is_active` check on every `get_current_user`. A token
  denylist is deferred (out of v1 scope).
- The role in the token can go stale within an access token's lifetime if an
  admin changes it; acceptable for v1 given the short lifetime.

## Alternatives considered

- **Server-side sessions (cookie + session store):** simpler revocation, but adds
  stateful infrastructure and a second model for the API. Rejected for a
  local-first, single-process app.
- **OAuth2 / third-party IdP:** overkill for an educational local app with no
  external users; adds a network dependency contrary to "runs offline".
- **Argon2 instead of bcrypt:** excellent, but bcrypt via passlib is ubiquitous,
  well-documented, and sufficient here; revisiting is cheap (passlib abstracts it).
```
