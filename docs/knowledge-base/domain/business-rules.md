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

## Rule #9 — Lab result flagging & visibility (§13, M8) ✅ v2

**Statement.** A doctor orders a lab on an encounter; clinical staff record result
values against it; each value is flagged **abnormal** if it falls outside its
(inclusive) reference range. Viewing a patient's labs follows the same
treating-relationship scoping as history (Rule #3) + consent (Rule #8).

**Why.** Labs are a distinct cross-role artifact: the *ordering* clinician, the
*recording* staffer, and the *patient* are often different people, so the rule
must separate who-can-order (owning doctor) from who-can-record (any clinical
staff) from who-can-view (scoped). Flagging at record time — with the reference
range stored alongside — keeps the abnormal marker explainable after the fact.

**Edge cases.**
- Reference bounds are **inclusive**; either bound may be open-ended (`None`); with
  no range a value is never abnormal.
- Results are **append-only** (§5.6): recording adds rows and moves the order to
  `resulted`; prior results are never edited.
- Only the **owning doctor** may order; only **clinical staff** may record; a
  patient may view **only their own** labs; a **non-treating doctor is denied**
  (audited `lab.read_denied`). Admin has no clinical read.

**Enforced in.** `app/domain/lab_rules.is_abnormal` (pure) +
`app/services/lab_service.py` (order/record/view, reusing
`access_scope.can_view_patient_history`). Models in `app/models/lab.py`.
**Tests.** `tests/domain/test_lab_rules.py`, `tests/services/test_lab_service.py`,
`tests/api/test_labs.py`, `tests/web/test_labs_web.py`,
`tests/api/test_lab_integration.py`.

## Rule #10 — Care-team messaging & event notifications (§13, M9) ✅ v2

**Statement.** A patient and a clinical-staff member exchange messages in a single
shared thread per (patient, staff) pair; only the two participants may read it.
Who may be the *staff* side follows the same treating-relationship scoping as
history (Rule #3): a doctor needs a treating relationship, a nurse may message any
patient, and an admin is never a care-conversation participant. Separately,
domain events (a message sent, an appointment booked/cancelled, a lab resulted, a
prescription written) raise an in-app **notification** for the affected user.

**Why.** Messaging must not become an open inbox — a patient's clinical
correspondents are exactly their care team, so reusing the §5.3 relationship
avoids inventing a second, divergent access rule. Notifications are a *derived
read-model*, not a clinical record: they are emitted as a best-effort side effect
inside the same unit of work as the event (so an event and its alert commit
together), and — unlike append-only clinical rows — the recipient may mark them
read.

**Edge cases.**
- A thread is **unique per (patient, staff) pair** (DB constraint); "starting a
  new conversation" with someone you already message reuses the existing thread.
- Messages are **append-only** (§5.6): never edited or deleted.
- A **non-treating doctor** and any **non-participant** are denied reading a thread
  (audited `message.read_denied`, committed so it survives the raise), mirroring
  the lab/history read-deny path.
- Notifications are **scoped to their owner**: `mark_read` refuses another user's
  notification (returns `False`, not an error) and is idempotent.
- An empty/whitespace message body is rejected (`ValidationError`).

**Enforced in.** `app/domain/messaging_rules.can_staff_message_patient` (pure) +
`app/services/messaging_service.py` (send/list/read, reusing
`encounter_repository.has_treating_relationship`) and
`app/services/notification_service.py` (the single `notify` choke point, plus
read/mark-read). Emission is wired into `appointment_service`, `lab_service`, and
`prescription_service`. Models in `app/models/messaging.py` +
`app/models/notification.py`.
**Tests.** `tests/domain/test_messaging_rules.py`,
`tests/services/test_messaging_service.py`,
`tests/services/test_notification_service.py`, `tests/api/test_messages.py`,
`tests/web/test_messaging_web.py`.

---

## Rule #11 — AI vitals assistant: rule-grounded, human-in-the-loop (§14, M12) ✅ v2

**Statement.** The vitals triage assistant produces a structured, advisory
`VitalsAssessment` (summary, urgency, red flags, recommended action, confidence)
to help staff prioritize a set of recorded vitals. The **deterministic, age-based
flags from Rule #5 (`flag_out_of_range`) are authoritative**: they are passed into
the model, the model may only *explain and prioritize* them, and it may never set
its own thresholds or contradict the rule. If a real flag exists, the assessment's
urgency can never be "routine" (a safety clamp bumps it to at least "elevated").
The assistant is **decision-support only** — a clinician always decides — and on
any model failure or refusal it **degrades** to a rules-only assessment rather than
failing the caller.

**Why.** A non-deterministic model must not silently override a validated clinical
rule — that would make patient-safety behavior unpredictable and untestable. So the
rule leads and the model explains, which keeps the safety-critical decision
deterministic while still giving staff a readable, prioritized summary. Framing it
as advisory (never diagnosis) honors the Non-Goals and the responsible-AI posture
(*AI in the loop, human at the center*). Degrading to rules-only means the feature
adds value even when the model is unavailable — the app never depends on a paid API
to function (mirrors the SQLite-default posture, ADR-0001/ADR-0006).

**Edge cases.**
- **All vitals normal** → urgency "routine", no red flags, confidence 1.0.
- **Model refuses / errors / times out** → rules-only assessment; a distinct audit
  action `llm.vitals_assessed_degraded` records that the fallback path ran.
- **Model returns "routine" despite a real flag** → clamped up to "elevated"
  (the deterministic flag wins).
- **Malformed model output** → re-asked within the retry budget, then a typed
  `SchemaValidationError`; the caller never sees a half-parsed object.
- **Offline / no API key (default)** → the deterministic **stub** provider serves a
  schema-valid response, so the flow works with no network or SDK.

**Enforced in.** `app/services/vitals_assistant_service.py` (composition, safety
clamp, degradation, audit; `assess_encounter_vitals` resolves the encounter's
age + latest reading and applies the §5.3 treating-relationship rule for doctors),
built on the LLM component layer `app/core/llm/` (`client.py` — the five
disciplines; `providers.py` — stub-default/opt-in real; `vitals_schema.py` — the
`VitalsAssessment` output contract). Ground-truth flags come from the pure
`app/domain/vitals_ranges.flag_out_of_range` (Rule #5). AI use is audited via
`services/audit_service.record_audit` (Rule #7:
`llm.vitals_assessed` / `…_degraded` / `…_denied`).
**Exposed to users (M12 exposure slice, c074).** API:
`POST /api/v1/encounters/{id}/vitals-assessment` (nurse or treating doctor;
`schemas/encounter.VitalsAssessmentOut`). Web: an HTMX "Get AI triage assist"
panel on the nurse vitals-entry screen (`web/clinical.vitals_assessment`,
`templates/encounters/partials/vitals_assessment.html`). Both use the configured
provider — the offline stub by default, or a real model when `HV_LLM_PROVIDER` +
`HV_LLM_API_KEY` are set. See
[ADR-0006](../adr/ADR-0006-llm-component-layer.md) and
[workflows/vitals-assistant.md](../workflows/vitals-assistant.md).
**Tests.** `tests/core/llm/test_llm_client.py`,
`tests/services/test_vitals_assistant_service.py`,
`tests/api/test_vitals_assessment.py`, `tests/web/test_vitals_assistant_web.py`.

---

## Rule #12 — Vitals trends read scoping (§15, M13) ✅ v2

**Statement.** A patient's vitals **series** (the same measurements over time, used for trend
charts) is readable under the **identical** rule as their medical history (Rule #3 / §5.3): a
patient sees only their own; a doctor needs a treating relationship; a nurse may read; an admin may
not. Sensitive encounters are filtered by the same consent gate as history (§5.8), so a staff
member without shared consent never sees vitals from a sensitive encounter — even in a chart.

**Why.** A chart is just another *read* of PHI, so it must not open a softer side-door than the
history page it sits beside. Reusing `can_view_patient_history` + `is_encounter_visible` (rather
than inventing a second predicate) guarantees the trend view and the history view can never drift
apart in what they expose. The read is audited (`vitals_series.read` / `vitals_series.read_denied`)
exactly like history (Rule #7).

**Edge cases.**
- **< 2 points** → the client shows an empty-state note instead of a chart (nothing to trend).
- **Consent-gated encounter** → its vitals are excluded from the series for staff without shared
  consent (identical to history visibility).
- **Chart JS unavailable / fetch fails** → the raw vitals remain listed on the page (progressive
  enhancement); no clinical data is hidden behind the script (ADR-0007).

**Enforced in.** `app/services/clinical_service.get_vitals_series` (authz + consent + audit) over
`app/repositories/encounter_repository.vitals_for_patient` (DAL join). Exposed read-only at
`GET /api/v1/patients/{id}/vitals-series` (`schemas/encounter.VitalsSeriesOut`); rendered by
Chart.js (vendored, [ADR-0007](../adr/ADR-0007-client-charting-vendored-chartjs.md)) on the history
page. See [workflows/vitals-trends.md](../workflows/vitals-trends.md).
**Tests.** `tests/api/test_vitals_series.py`, `tests/web/test_vitals_trends_web.py`.
