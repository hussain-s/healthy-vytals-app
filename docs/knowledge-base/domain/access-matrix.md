# Access-Control Matrix — roles × actions, with rationale

> The RBAC table an AI **cannot** infer from code alone: *why* each cell is what
> it is. Enforced by coarse route guards (`require_roles`, `app/core/deps.py`) +
> fine-grained ownership/treating-relationship checks in the service layer.
> Mirrors DESIGN §6; this file adds the reasoning per cell.
>
> **Status by phase:** ✅ implemented in Phase 1 · ⏳ arrives in a later phase
> (kept here so the target model is visible while building toward it).

## Roles

| Role | Essence | Least-privilege boundary |
|---|---|---|
| **Patient** | Receives care | Sees only *their own* data; can self-register and manage their own appointments. |
| **Nurse** | Triages, records vitals | Clinical *staff*, but **not** a clinical author — records vitals, never diagnoses/prescribes. |
| **Doctor** | Diagnoses, prescribes | The only **clinical author**; sees full history only for patients they *treat* (§5.3). |
| **Admin** | Operates the clinic | Manages accounts + reads the audit log; **no clinical authoring rights at all**. |

## Matrix

| Resource / Action | Patient | Nurse | Doctor | Admin | Status |
|---|---|---|---|---|---|
| Register self (patient) | ✅ | — | — | — | ✅ |
| Provision staff account | — | — | — | ✅ | ✅ |
| Log in / refresh / view self (`/me`) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Own profile (read/write) | ✅ | ✅ | ✅ | ✅ | ⏳ |
| List / deactivate users | — | — | — | ✅ | ⏳ (E1) |
| Availability slots | read | read | **create own** | read | ⏳ (Phase 2) |
| Book / cancel appointment | **own** | on behalf (ward) | own calendar | all | ⏳ (Phase 2) |
| Advance appointment state | — | check-in | begin/complete/no-show | — | ⏳ (Phase 2) |
| Vitals | read own | **create/read** | read | read | ⏳ (Phase 3) |
| Diagnosis | read own | read | **create** | read | ⏳ (Phase 3) |
| Prescription | read own | read | **create (safety-checked)** | read | ⏳ (Phase 4) |
| Addendum (corrections) | — | on own entries | on own entries | — | ⏳ (Phase 3) |
| Audit log | — | — | — | **read** | ⏳ (E2/E3) |

## Rationale per non-obvious cell

- **Only patients self-register; staff are provisioned.** Real clinics do not let
  someone self-declare as a doctor. Self-service creates a PATIENT; an admin
  creates staff with an explicit role (`provision_staff` rejects PATIENT).
- **Nurse is clinical staff but not a clinical author.** Nurses record vitals and
  prep encounters but do **not** author diagnoses or prescriptions. Encoded as
  `CLINICAL_AUTHORS = {doctor}` (`app/core/roles.py`).
- **Admin has no clinical authoring rights.** Separation of duties: the role that
  administers accounts and *reads the audit log* must not also create the clinical
  records the audit log oversees. That is why Admin is excluded from vitals,
  diagnosis, and prescription authoring.
- **Only Admin reads the audit log.** If a clinical role could read/alter the
  audit trail, the trail could not be trusted to record their own PHI access.
  Encoded as `AUDIT_READERS = {admin}`.
- **Doctor sees full history only for *treated* patients (§5.3).** Being a doctor
  is necessary but not sufficient; the fine-grained treating-relationship check in
  the service layer decides *which* patients. Role alone (coarse guard) cannot
  express this, which is exactly why authorization is two-layered.
- **Accounts are deactivated, not deleted (E1).** Deleting a user would orphan the
  clinical and audit records that reference them. `is_active=False` disables login
  and `get_current_user` immediately while preserving history.

## Where each layer lives

- **Coarse (role) checks:** `require_roles(...)` guards on routes — e.g.
  `POST /api/v1/users` requires `Role.ADMIN`.
- **Fine (ownership/relationship) checks:** service functions — e.g. a patient may
  read only their own history; a doctor only patients they treat (Phase 3).
```
