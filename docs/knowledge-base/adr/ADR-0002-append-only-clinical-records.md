# ADR-0002 — Append-only clinical records; corrections via addenda

- **Status:** Accepted
- **Date:** 2026-08-08
- **Related:** DESIGN §5.6; [business-rules.md](../domain/business-rules.md) Rule #6

## Context
The medical record is a legal document. Editing or deleting a diagnosis, vitals
reading, or encounter in place would destroy history and make the record
untrustworthy and un-auditable.

## Decision
Clinical records (`Encounter`, `Vitals`, `Diagnosis`) are **append-only**. There
is deliberately **no** update or delete operation for them:
- the service layer exposes only *create* and *addendum* operations;
- there is no PUT/DELETE route for clinical resources (verified by test);
- a correction is a new `Addendum` row referencing the target via a lightweight
  polymorphic `(target_type, target_id)` pair — one addendum table serves every
  clinical entity. Addenda are clinical-staff-only.

This mirrors an accounting reversing entry: you never erase, you append a
correction.

## Consequences
**Positive:** a complete, tamper-evident history; simple, safe audit story;
corrections are first-class and attributable.
**Negative / mitigations:** reading "the current truth" means reading the record
plus its addenda; UIs must present both. Acceptable — and honest — for a medical
record. The immutability is enforced in the service layer (not the DB), so a
future direct-SQL path must respect it; the KB and tests make the rule explicit.

## Alternatives considered
- **Mutable rows with an audit table:** common but weaker — the primary row can
  still be silently changed; the audit table becomes the only truth. Rejected.
- **Soft-delete flags:** hides rather than corrects; muddies "what was true when".
  Rejected in favor of addenda.
