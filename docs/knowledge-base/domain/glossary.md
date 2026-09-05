# Glossary — ubiquitous language

> The shared vocabulary of HealthyVytals. Terms are defined the way the *domain*
> means them, with the distinctions that matter (e.g. appointment vs. encounter)
> that an AI reading only code would likely conflate. Grows each phase; entries
> marked ⏳ name concepts that arrive in a later phase but are defined now so the
> language is stable.

## Identity & access (Phase 1)

- **User** — the base account: email, bcrypt password hash, `role`, `is_active`.
  The authentication anchor; role-specific attributes live on a profile.
- **Role** — one of **patient**, **nurse**, **doctor**, **admin**. Drives
  authorization. Stored as its string value (`app/core/roles.py`).
- **Profile** — a 1:1 extension of a User holding role-specific attributes:
  *PatientProfile* (demographics/insurance/emergency contact), *DoctorProfile*
  (specialty, license no.), *NurseProfile* (ward). Admin has no profile.
- **Clinical staff** — nurses and doctors (`CLINICAL_STAFF`). Distinct from
  **staff** (nurse + doctor + admin) and from **clinical author** (doctor only).
- **Clinical author** — a role permitted to author immutable clinical records
  (diagnoses, prescriptions). Only **doctor** (`CLINICAL_AUTHORS`).
- **Self-registration** — the patient-only signup path (story A1). Creates a
  PATIENT account + PatientProfile.
- **Provisioning** — admin creation of a *staff* account with an explicit role
  (story A2). Never creates a patient.
- **Deactivation** — setting `is_active=False` instead of deleting an account
  (story E1); disables login/session while preserving history and audit links.

## Tokens & auth (Phase 1)

- **Access token** — short-lived JWT proving identity on each request; carries
  `sub` (user id) and `role`. `type: "access"`.
- **Refresh token** — long-lived JWT used only to obtain new access tokens;
  carries no role. `type: "refresh"`. Cannot be used as an access token, or
  vice versa (enforced by `decode_token`).
- **Bearer vs. cookie** — the API sends the access token as an
  `Authorization: Bearer` header; the browser UI carries it in an HttpOnly
  `hv_access` cookie. Both resolve to the same user via `get_current_user`.
- **Coarse vs. fine authorization** — *coarse* = role gate (`require_roles`);
  *fine* = ownership / treating-relationship checks in the service layer.

## Auditing (Phase 1)

- **Audit log** — append-only record of who did what, when. Written via
  `record_audit` inside the same transaction as the audited action, so the two
  commit or roll back together. Action names use `resource.verb`
  (e.g. `auth.login`, `user.provision`).
- **PHI (Protected Health Information)** — patient-identifying medical data.
  Every read/write of PHI must be audited (§5.7).

## Clinical domain (defined now; ⏳ implemented later)

- **Appointment** ⏳ — a *scheduled* patient↔doctor meeting in a slot, moving
  through a state machine (requested → confirmed → checked_in → in_progress →
  completed, with cancel/no-show branches). §5.1.
- **Encounter** ⏳ — the *clinical record of a visit* that actually happened;
  created from an appointment and holds vitals, diagnoses, prescriptions. An
  **appointment is the plan; an encounter is the record** — they are not the same
  thing, and conflating them is the classic modeling error this glossary guards
  against.
- **Availability slot** ⏳ — a bookable window a doctor publishes (§5.2).
- **Vitals** ⏳ — nurse-recorded measurements (BP, HR, temp, SpO₂, …); out-of-range
  values (age-dependent, §5.5) flag the encounter.
- **Diagnosis** ⏳ — a doctor-authored ICD-style finding on an encounter;
  append-only.
- **Addendum** ⏳ — an immutable *correction* appended to a clinical record;
  clinical records are never edited in place (§5.6).
- **Prescription** ⏳ — a doctor-authored medication order, subject to safety
  checks: allergy hard-block, drug-interaction warning, controlled-substance
  refill caps (§5.4).
- **Treating relationship** ⏳ — the link (appointment/encounter) that lets a
  specific doctor see a specific patient's full history (§5.3).
- **Consent gating** ⏳ — sensitive categories require an explicit consent flag to
  be visible, even to otherwise-authorized staff (§5.8).
```
