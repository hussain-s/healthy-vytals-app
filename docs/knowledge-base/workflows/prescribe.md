# Workflow — Prescribing with safety checks (stories D1–D5)

How a doctor prescribes within an encounter and how the §5.4 safety checks gate
it. See [business-rules.md](../domain/business-rules.md) Rule #4.

## Sequence

```mermaid
sequenceDiagram
    actor Doctor
    participant API as api/v1/prescriptions
    participant Svc as prescription_service
    participant Repo as prescription_repository
    participant Dom as domain/prescription_safety
    participant DB as SQLite

    Doctor->>API: POST /prescriptions {encounter, medication, dose, refills, override?}
    API->>Svc: prescribe(...)
    Svc->>Repo: load encounter (404) + owning-doctor check (403)
    Svc->>Repo: load medication (404)
    Svc->>Repo: allergy_terms + interacting_active_medication_ids
    Svc->>Dom: evaluate_prescription(drug, context, refills, override)
    alt allergy match
        Dom-->>Svc: blocked reason=allergy (non-overridable)
        Svc->>DB: audit prescription.blocked (committed)
        API-->>Doctor: 409 {reason: allergy}
    else controlled + refills over cap
        Dom-->>Svc: blocked reason=refill_cap
        Svc->>DB: audit prescription.blocked (committed)
        API-->>Doctor: 409 {reason: refill_cap}
    else interaction and not overridden
        Dom-->>Svc: blocked reason=interaction
        Svc->>DB: audit prescription.blocked (committed)
        API-->>Doctor: 409 {reason: interaction} (retry with override)
    else allowed (clean, or interaction overridden)
        Svc->>DB: create Prescription, audit prescription.create
        API-->>Doctor: 201 PrescriptionOut
    end
```

## Notes
- **Severity ladder:** allergy (absolute) > refill cap > interaction (overridable).
  Allergy is evaluated first so it can never be bypassed by an override.
- **Blocks are audited too** (`prescription.blocked`, committed independently) —
  an attempted unsafe prescription is itself a recordable event.
- **Web path:** the encounter page's prescribe form (`/clinical/encounters/{id}/
    prescriptions`) posts to the same service and swaps in the prescriptions list
  partial, showing the block reason inline; the override checkbox retries.
