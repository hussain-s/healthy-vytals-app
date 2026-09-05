# Traceability — business rules → tests

Every business rule in DESIGN §5 maps to named tests, at one or more layers:
**domain** (pure unit tests), **service** (DB, no HTTP), **api** (HTTP), and where
relevant a phase **exit-gate integration** test. This is the "spot-check that each
rule maps to a test" from DESIGN §10, made explicit.

Run everything from `backend/`: `../.venv/bin/python -m pytest`. Full suite at
last update: **250 passing**.

| Rule (DESIGN §5) | Enforced in | Pinning tests |
|---|---|---|
| **§5.1** Appointment state machine | `domain/appointment_state.py` | `tests/domain/test_appointment_state.py` (9); `tests/services/test_appointment_service.py` (transitions); `tests/api/test_appointments.py`, `tests/api/test_scheduling_integration.py` |
| **§5.2** Slot conflict / buffer / cancel cutoff | `domain/scheduling_rules.py` | `tests/domain/test_scheduling_rules.py` (11); `tests/services/test_appointment_service.py`; `tests/services/test_booking_concurrency.py` (unique-slot race); `tests/api/test_scheduling_integration.py` (double-book, late-cancel) |
| **§5.3** Treating-relationship scoping | `domain/access_scope.py` | `tests/domain/test_access_scope.py`; `tests/services/test_clinical_service.py` (allow/deny+audit); `tests/api/test_encounters.py`, `tests/api/test_clinical_integration.py` |
| **§5.4** Prescription safety | `domain/prescription_safety.py` | `tests/domain/test_prescription_safety.py` (9); `tests/services/test_prescription_service.py`; `tests/api/test_prescriptions.py`, `tests/api/test_prescription_integration.py` |
| **§5.5** Age-based vitals ranges | `domain/vitals_ranges.py` | `tests/domain/test_vitals_ranges.py` (7, incl. same-reading-differs-by-age); `tests/services/test_clinical_service.py` (record_vitals flags); `tests/api/test_clinical_integration.py` |
| **§5.6** Append-only clinical records | `services/clinical_service.py` (no mutators) | `tests/services/test_clinical_service.py` (addendum staff-only); `tests/api/test_clinical_integration.py::test_append_only_no_delete_endpoint` (no PUT/DELETE) |
| **§5.7** Mandatory audit logging | `services/audit_service.py` | `tests/services/test_audit_service.py` (flush/commit/rollback); `tests/api/test_rbac_integration.py`, `test_clinical_integration.py`, `test_prescription_service.py` (audit rows incl. failures) |
| **§5.8** Consent gating | `domain/access_scope.is_encounter_visible` | `tests/domain/test_access_scope.py` (consent cases); `tests/services/test_clinical_service.py::test_sensitive_encounter_hidden_*` |

## RBAC / access matrix
Coarse role gating (`require_roles`) and fine ownership checks are pinned by
`tests/core/test_deps.py` (guard allow/deny), `tests/api/test_users.py` (admin-only
provisioning), `tests/api/test_rbac_integration.py` (Phase 1 exit gate: all roles
log in, forbidden → 403, audit rows), and the per-domain API tests above.

## Notes
- Each pure rule is tested **without** a DB or HTTP (fast, isolated) and again at
  the integration boundary, so a regression is caught at the closest layer.
- New rules must add a row here in the same slice (Definition of Done, §9A.2).
