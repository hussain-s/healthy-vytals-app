# Workflow — Triage → consultation (stories C1–C5)

The clinical visit: from a nurse recording vitals to a doctor diagnosing, with
the scoping and immutability rules that govern it. See
[business-rules.md](../domain/business-rules.md) #3 (scoping), #5 (vitals), #6
(append-only), #8 (consent).

## Sequence

```mermaid
sequenceDiagram
    actor Doctor
    actor Nurse
    actor Patient
    participant API as api/v1/encounters
    participant Svc as clinical_service
    participant Dom as domain (vitals_ranges / access_scope)
    participant Repo as repositories
    participant DB as SQLite

    Doctor->>API: POST /encounters {appointment_id}
    API->>Svc: open_encounter(doctor, appointment_id)
    Svc->>Repo: get_by_appointment (idempotent)
    Svc->>DB: create Encounter, audit encounter.open
    API-->>Doctor: 201 EncounterOut

    Nurse->>API: POST /encounters/{id}/vitals {readings}
    API->>Svc: record_vitals(nurse, id, reading)
    Svc->>Repo: get patient profile (age)
    Svc->>Dom: flag_out_of_range(age, reading)
    Dom-->>Svc: flags (age-banded)
    Svc->>DB: create Vitals(flags), audit vitals.record
    API-->>Nurse: 201 VitalsOut (flags)

    Doctor->>API: POST /encounters/{id}/diagnoses {icd, desc}
    API->>Svc: add_diagnosis (owning-doctor check)
    Svc->>DB: create Diagnosis, audit diagnosis.create
    API-->>Doctor: 201 DiagnosisOut

    Patient->>API: GET /encounters/history/{patient_id}
    API->>Svc: get_patient_history(viewer, role, patient)
    Svc->>Dom: can_view_patient_history(...) [Rule #3]
    alt not allowed
        Svc->>DB: audit history.read_denied (committed)
        API-->>Patient: 403
    else allowed
        Svc->>DB: audit history.read
        Svc->>Dom: is_encounter_visible(...) per record [Rule #8 consent]
        API-->>Patient: 200 [visible encounters]
    end
```

## Notes
- **Roles:** nurse records vitals; doctor opens/diagnoses; corrections are
  addenda (append-only, Rule #6). No one edits or deletes a clinical record.
- **Two gates on reads:** history-level access (Rule #3) then per-record consent
  (Rule #8). Denials are audited.
- **Age drives flags:** the same vitals value can be normal or abnormal depending
  on the patient's age (Rule #5).
