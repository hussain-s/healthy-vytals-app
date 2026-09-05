# Business Rules — the "knowledge-base gold"

> The non-obvious rules that govern HealthyVytals, each with its **why**, its
> **edge cases**, where it is **enforced** in code, and the **tests** that pin it.
> An AI reading only the source could see *that* these checks exist; this file
> explains *why* they are shaped the way they are — the difference the project
> exists to demonstrate.
>
> Numbering follows DESIGN §5. Rules are added as each phase implements them;
> entries marked ⏳ are defined in DESIGN but not yet built.

---

## Rule #1 — Appointment state machine (§5.1)

**Statement.** An appointment moves only along legal transitions, and *who* may
trigger each transition is role-gated:

```
requested ──confirm(doctor)──▶ confirmed ──check_in(nurse)──▶ checked_in
   ──begin(doctor)──▶ in_progress ──complete(doctor)──▶ completed

branches:
  requested|confirmed|checked_in ──cancel(patient|nurse|doctor)──▶ cancelled
  confirmed|checked_in            ──no_show(nurse|doctor)──▶ no_show
  confirmed|checked_in            ──reschedule(patient|doctor)──▶ requested
```

**Why.** A clinical visit is a real-world process with a fixed order: you cannot
complete a visit that never began, and you cannot check someone in for a visit
the doctor hasn't confirmed. Encoding this as an explicit state machine (rather
than a free-form `status` string) makes illegal sequences *impossible* and makes
the rules auditable and testable. Role-gating mirrors real responsibilities: a
patient can cancel their own visit but cannot mark themselves "completed"; a
nurse checks patients in; only a doctor performs the clinical steps.

**Edge cases.**
- Terminal states (`completed`, `cancelled`, `no_show`) have **no** outgoing
  transitions — nothing can reopen them.
- A legal transition attempted by the wrong role fails distinctly from an illegal
  transition, so the error message is honest ("role X may not …" vs "cannot … in
  state Y"). Both surface as HTTP **409**.
- Cancelling frees the slot (see Rule #2); other transitions do not.

**Enforced in.** `app/domain/appointment_state.py` (pure table `_TRANSITIONS` +
`assert_transition_allowed`) → called by
`app/services/appointment_service.change_status`. Raises `IllegalTransition`
(`app/core/exceptions.py`), mapped to 409.

**Tests.** `tests/domain/test_appointment_state.py` (happy path, illegal-from-
state, role gating, terminal inertness); `tests/services/test_appointment_service.py`
(service-level lifecycle + ownership); `tests/api/test_appointments.py` and
`tests/api/test_scheduling_integration.py` (HTTP 409s + full lifecycle).

---

## Rule #2 — Slot conflict, buffer, and cancellation cutoff (§5.2)

**Statement.**
1. A doctor cannot have two overlapping appointments.
2. A configurable **buffer** (default 10 min, `HV_APPOINTMENT_BUFFER_MINUTES`)
   must separate consecutive appointments.
3. A cancellation is always **allowed**, but if it occurs within the **cutoff**
   window (default 24 h, `HV_CANCELLATION_CUTOFF_HOURS`) before the start it is
   **flagged late** (`cancelled_late = True`) rather than blocked.

**Why.** Double-booking a clinician is a scheduling error with real consequences;
the buffer reflects that back-to-back appointments need turnaround time (notes,
room reset). The cutoff models a real cancellation policy (a late cancel may incur
a fee or affect metrics) **without** denying care — so we record the fact instead
of refusing the cancellation.

**Design choices worth knowing.**
- Slots are **half-open intervals** `[start, end)`: a slot ending at 10:00 and one
  starting at 10:00 do **not** overlap. This makes "back-to-back" bookings natural
  and the buffer the *only* thing that separates adjacent appointments.
- The conflict check widens each existing appointment by the buffer on *both*
  sides, then tests overlap — so a new booking within `buffer` minutes of another
  is rejected.
- The rule thresholds live in `Settings` and are **passed into** the pure domain
  functions; the domain never reads config itself (keeps it pure/testable).

**Edge cases.**
- `buffer = 0` reduces the check to a pure overlap test.
- A cancellation for an appointment that has already started counts as late.
- Only *blocking* appointment states occupy time for conflict purposes
  (`requested/confirmed/checked_in/in_progress`); `cancelled`/`no_show`/`completed`
  do not block new bookings.
- **Race safety:** two patients racing for the last slot are stopped by the unique
  constraint on `appointments.slot_id` — at most one insert wins; the other gets
  an IntegrityError and rolls back. This is the last-line guard behind the
  `is_booked` flag and the conflict scan.

**Enforced in.** `app/domain/scheduling_rules.py` (`conflicts_with_buffer`,
`is_late_cancellation`, `windows_overlap`, `TimeWindow`) → used by
`app/services/appointment_service.py` (`publish_slot`, `book_appointment`,
`change_status`). DB guard: `unique(slot_id)` on `appointments`.

**Tests.** `tests/domain/test_scheduling_rules.py` (overlap, buffer both ways,
cutoff cases); `tests/services/test_appointment_service.py` (publish/book conflict,
late-flag); `tests/services/test_booking_concurrency.py` (unique-constraint race);
`tests/api/test_scheduling_integration.py` (double-book 409, late-cancel flag).

---

## Rule #3 — Treating-relationship scoping (§5.3) ✅ Phase 3

**Statement.** A doctor may read a patient's full history **only if** they have a
treating relationship (a shared appointment or encounter). A patient reads only
their own; a nurse may read (triage support); an admin gets **no** clinical read.

**Why.** "Is a doctor" is necessary but not sufficient to see a given patient's
PHI — the minimum-necessary principle. This is the canonical example of a rule
role-based guards *cannot* express, which is why authorization is two-layered:
the coarse route guard (`require_roles`) admits clinicians; the fine service
check (`can_view_patient_history`) decides *which* patients.

**Edge cases.**
- A denied read is **audited** (`history.read_denied`, committed so it survives
  the 403 rollback) — attempted access to PHI is itself security-relevant.
- The relationship counts an appointment even before an encounter opens, so a
  doctor a patient just booked with can prepare.

**Enforced in.** `app/domain/access_scope.can_view_patient_history` (pure) +
`EncounterRepository.has_treating_relationship` (the fact) →
`clinical_service.get_patient_history`.
**Tests.** `tests/domain/test_access_scope.py`, `tests/services/test_clinical_service.py`,
`tests/api/test_encounters.py`, `tests/api/test_clinical_integration.py`.

## Rule #4 — Prescription safety: allergy / interaction / refill (§5.4) ✅ Phase 4

**Statement.** Before a medication is prescribed, three checks run, differing in
**severity**:
1. **Allergy → HARD BLOCK (non-overridable).** If the drug's name *or* its class
   matches a recorded patient allergy, prescribing is refused. No override.
2. **Drug interaction → WARN (overridable).** If the drug interacts with one of
   the patient's *active* medications, prescribing is blocked **unless** the
   prescriber sets `override_interaction`, acknowledging the risk.
3. **Controlled substance → REFILL CAP.** A controlled substance may not be
   prescribed with more than `MAX_CONTROLLED_REFILLS` (0) refills.

**Why the severities differ (the non-obvious part).** Prescribing into a known
allergy can be fatal and is never acceptable — hence an absolute block.
Interacting drugs, by contrast, are routinely co-prescribed with monitoring, so
the rule is a *speed bump* that forces explicit acknowledgment, not a wall.
Controlled-substance refill caps reflect regulatory limits on abuse potential.

**Edge cases.**
- **Allergy is checked first**, so it's always the reported reason and an
  `override_interaction` can never smuggle a drug past an allergy.
- Allergy matches on **name OR drug class** (a penicillin-class allergy blocks
  amoxicillin).
- Only the patient's **active** prescriptions count for interactions.
- An overridden interaction still **records the warning** for the record.
- Every attempt is audited: `prescription.create` on success,
  `prescription.blocked` (committed, survives the 409 rollback) on a block.

**Enforced in.** `app/domain/prescription_safety.evaluate_prescription` (pure) +
`app/repositories/prescription_repository.py` (allergy terms, interacting active
meds) → `app/services/prescription_service.prescribe`. Typed error
`UnsafePrescription` (409) carries the block `reason` in details.
**Tests.** `tests/domain/test_prescription_safety.py`,
`tests/services/test_prescription_service.py`,
`tests/api/test_prescriptions.py`, `tests/api/test_prescription_integration.py`.

## Rule #5 — Age-based vitals ranges (§5.5) ✅ Phase 3

**Statement.** Normal vitals ranges vary by patient **age**; a reading outside
its age band flags the encounter (e.g. `heart_rate_high`).

**Why.** A fixed threshold would misclassify children — an infant's normal heart
rate (100–160) is "tachycardia" by adult standards. Age-banding encodes real
physiology, and the flags surface an abnormal visit for attention rather than
blocking anything.

**Edge cases.** Only recorded (non-null) measurements are checked; the same HR
(150) is normal for an infant and high for an adult (the pinned test); a missing
DOB falls back to the adult band (documented, intentional). Flags are a snapshot
stored with the reading, append-only.

**Enforced in.** `app/domain/vitals_ranges.flag_out_of_range` (pure) →
`clinical_service.record_vitals` (supplies age from `PatientProfile`).
**Tests.** `tests/domain/test_vitals_ranges.py` (incl. same-reading-differs-by-age).

## Rule #6 — Immutable clinical records / addenda (§5.6) ✅ Phase 3

**Statement.** Encounters, vitals, and diagnoses are **append-only**: never edited
or deleted in place. A correction is a new **Addendum** referencing the target
record.

**Why.** The medical record is a legal document; altering history destroys
trust and auditability (analogous to an accounting reversing entry). Preserving
the original + a correction trail is the safe, lawful pattern.

**Edge cases / how it's enforced.** The service layer exposes only *create* and
*addendum* operations — there is deliberately **no** update/delete method for
clinical rows, and **no** PUT/DELETE route (the API test asserts 404/405).
Addenda are clinical-staff-only. `target_type`+`target_id` let one Addendum table
annotate any clinical entity.
**Enforced in.** `clinical_service` (no mutators) + `models/clinical.Addendum`.
**Tests.** `tests/api/test_clinical_integration.py::test_append_only_no_delete_endpoint`,
`tests/services/test_clinical_service.py::test_addendum_requires_clinical_staff`.

## Rule #7 — Mandatory audit logging (§5.7) ✅ Phase 1

See [access-matrix.md](access-matrix.md) and ADR-0005 (audit) for #7; the audit
trail is written via `app/services/audit_service.record_audit` on every security-
and PHI-relevant action, append-only, inside the acting transaction (failure
audits committed independently so a rolled-back action still records the attempt).

## Rule #8 — Consent gating on sensitive categories (§5.8) ✅ Phase 3

**Statement.** An encounter marked **sensitive** (e.g. mental-health notes) is
hidden from otherwise-authorized staff **unless** the patient has shared consent
(`consent_shared`). The patient always sees their own records.

**Why.** Some categories of PHI carry extra legal/ethical protection; being a
treating clinician is not automatically enough to view them. Consent is the
patient's control.

**Edge cases.** Self-access is never gated (consent governs *sharing*, not the
patient's own view); non-sensitive records follow normal rules; the gate is a
*per-record* filter applied **after** the history-level access check (Rule #3).
**Enforced in.** `app/domain/access_scope.is_encounter_visible` (pure) →
`clinical_service.get_patient_history`. Flags on `models/clinical.Encounter`.
**Tests.** `tests/domain/test_access_scope.py` (consent cases),
`tests/services/test_clinical_service.py::test_sensitive_encounter_hidden_*`.
