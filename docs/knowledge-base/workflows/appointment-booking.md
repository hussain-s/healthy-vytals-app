# Workflow — Appointment booking (stories B1–B3)

How a patient books a doctor's published slot, and the checks that run. See
[business-rules.md](../domain/business-rules.md) Rule #2 for the conflict/buffer
reasoning.

## Sequence

```mermaid
sequenceDiagram
    actor Doctor
    actor Patient
    participant API as api/v1/appointments
    participant Svc as appointment_service
    participant Dom as domain/scheduling_rules
    participant Repo as repositories
    participant DB as SQLite

    Doctor->>API: POST /appointments/slots {start,end}
    API->>Svc: publish_slot(doctor_id, start, end)
    Svc->>Dom: conflicts_with_buffer(candidate, existing, buffer)
    Dom-->>Svc: no conflict
    Svc->>Repo: add(AvailabilitySlot)
    Svc->>DB: audit slot.publish
    API-->>Doctor: 201 SlotOut

    Patient->>API: GET /appointments/slots/open/{doctor_id}
    API-->>Patient: [open slots]

    Patient->>API: POST /appointments {slot_id, reason}
    API->>Svc: book_appointment(patient_id, slot_id, reason)
    Svc->>Repo: get slot
    alt slot missing
        Svc-->>API: NotFound (404)
    else slot already booked
        Svc-->>API: SlotConflict (409)
    else ok
        Svc->>Dom: conflicts_with_buffer(slot window, doctor's active appts, buffer)
        alt buffer conflict
            Svc-->>API: SlotConflict (409)
        else clear
            Svc->>Repo: slot.is_booked = True
            Svc->>Repo: add(Appointment status=requested)
            Svc->>DB: audit appointment.book
            API-->>Patient: 201 AppointmentOut
        end
    end
```

## Notes
- **Two conflict checks:** publishing rejects a slot overlapping the doctor's
  booked time; booking re-checks at commit time. The unique `slot_id` constraint
  is the final race guard (Rule #2).
- **Web path:** the HTMX booking page (`/appointments/book`) posts to the same
  service and swaps in a confirmation/error partial — identical behavior, HTML
  instead of JSON.
