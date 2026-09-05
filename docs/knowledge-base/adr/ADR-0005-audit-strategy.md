# ADR-0005 — Audit strategy: service-layer, append-only, atomic

- **Status:** Accepted
- **Date:** 2026-08-08
- **Related:** DESIGN §5.7, §7.4; [business-rules.md](../domain/business-rules.md) Rule #7

## Context
Every read or write of PHI must be recorded (who, what, when, which patient) —
the HIPAA-style accountability requirement. The record must be trustworthy and
must survive even failed/denied attempts.

## Decision
- **Service-layer, not middleware.** The audit row is written by
  `services/audit_service.record_audit`, called from each use case, because only
  the service knows the affected `patient_id` and the semantic action. (Coarse
  request logging via middleware remains possible but is not the source of truth.)
- **Append-only** `audit_logs` table; actions use a `resource.verb` convention
  (`auth.login`, `history.read`, `prescription.blocked`, …).
- **Atomic by default:** the audit write shares the caller's unit of work, so an
  action and its audit row commit or roll back together — no orphan or missing
  audit for a successful/failed action.
- **`commit=True` for failure audits:** when an action will *raise* (failed login,
  denied history read, blocked prescription), the audit is committed immediately
  so it survives the request rollback the raise triggers. Used only where the
  audit row is the sole pending write.
- **Nullable actor** so unauthenticated events (failed login) are still recorded;
  **`SET NULL`** FKs so deleting a user never erases their audit history.
- **Only admins read the audit log** (separation of duties — see access-matrix).

## Consequences
**Positive:** a complete, attributable trail including denials and blocks;
consistent shape; a single choke point to evolve. Powers story E2 (filter by
user/patient/date) via indexed columns.
**Negative / mitigations:** every PHI path must remember to call `record_audit`;
we mitigate by routing PHI access through services (one place per use case) and
asserting audit rows in integration tests.

## Alternatives considered
- **Middleware-only auditing:** can't name the patient/resource semantically and
  misses domain-level context. Kept as optional coarse logging, not the record.
- **DB triggers:** move the rule into the database, away from the domain and the
  KB, and are backend-specific. Rejected.
