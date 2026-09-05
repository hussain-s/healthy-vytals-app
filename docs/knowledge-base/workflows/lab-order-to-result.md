# Workflow — Lab order → result → review (v2 M8)

The cross-role lab flow. See [business-rules.md](../domain/business-rules.md)
Rule #9 (flagging + visibility) and Rule #3 (treating-relationship scoping).

## Sequence

```mermaid
sequenceDiagram
    actor Doctor
    actor Nurse
    actor Patient
    participant API as api/v1/labs (+ web/clinical)
    participant Svc as lab_service
    participant Dom as domain/lab_rules
    participant DB as SQLite

    Doctor->>API: order lab on encounter {test_code, test_name}
    API->>Svc: order_lab (must own the encounter)
    Svc->>DB: LabOrder(status=ordered), audit lab.order
    API-->>Doctor: 201 order

    Nurse->>API: record result {analyte, value, ref range}
    API->>Svc: record_result (clinical staff only)
    Svc->>Dom: is_abnormal(value, ref_low, ref_high)
    Dom-->>Svc: abnormal?
    Svc->>DB: LabResult(abnormal), order.status=resulted, audit lab.result
    API-->>Nurse: 201 result (flagged if abnormal)

    Patient->>API: view my labs
    API->>Svc: get_patient_labs(viewer, role, patient)
    Svc->>Dom: can_view_patient_history(...) [Rule #3]
    alt not allowed
        Svc->>DB: audit lab.read_denied (committed)
        API-->>Patient: 403
    else allowed
        Svc->>DB: audit lab.read
        API-->>Patient: 200 orders + results (abnormal flagged)
    end
```

## Notes
- **Three roles, three permissions:** owning doctor orders; any clinical staff
  records; viewing is scoped (patient=own, treating doctor, nurse; admin none).
- **Append-only:** recording adds result rows and flips the order to `resulted`;
  nothing is edited in place.
- **Web:** doctor orders/reviews on the encounter page; nurse works the
  `/clinical/labs/queue`; patient sees `/clinical/labs`. All HTMX partial swaps.
