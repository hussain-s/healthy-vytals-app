# Workflow — Appointment lifecycle: cancel & no-show (stories B4, B6)

How an appointment advances through its states after booking, and the two exit
branches (cancel, no-show). See [business-rules.md](../domain/business-rules.md)
Rule #1 for the full transition table and role gating.

## State diagram

```mermaid
stateDiagram-v2
    [*] --> requested: book (patient)
    requested --> confirmed: confirm (doctor)
    confirmed --> checked_in: check_in (nurse)
    checked_in --> in_progress: begin (doctor)
    in_progress --> completed: complete (doctor)

    requested --> cancelled: cancel (patient/staff)
    confirmed --> cancelled: cancel (patient/staff)
    checked_in --> cancelled: cancel (patient/staff)

    confirmed --> no_show: no_show (nurse/doctor)
    checked_in --> no_show: no_show (nurse/doctor)

    confirmed --> requested: reschedule (patient/doctor)
    checked_in --> requested: reschedule (patient/doctor)

    completed --> [*]
    cancelled --> [*]
    no_show --> [*]
```

## Cancel sequence (with late flag + slot release)

```mermaid
sequenceDiagram
    actor Patient
    participant API as api/v1/appointments
    participant Svc as appointment_service
    participant SM as domain/appointment_state
    participant Dom as domain/scheduling_rules
    participant DB as SQLite

    Patient->>API: POST /appointments/{id}/transitions/cancel
    API->>Svc: change_status(actor, role, id, CANCEL)
    Svc->>Svc: ownership check (patient owns appt?)
    Svc->>SM: assert_transition_allowed(status, CANCEL, role)
    alt illegal or wrong role
        SM-->>API: IllegalTransition (409)
    else allowed
        Svc->>DB: slot.is_booked = False  (release slot)
        Svc->>Dom: is_late_cancellation(now, slot.start, cutoff)
        Dom-->>Svc: late? -> cancelled_late
        Svc->>DB: status = cancelled, audit appointment.cancel
        API-->>Patient: 200 AppointmentOut (cancelled_late set)
    end
```

## Notes
- **Ownership** is a *fine* check (a patient may cancel only their own
  appointment) that the coarse role gate cannot express — hence it lives in the
  service, not `require_roles`.
- **Cancelling releases the slot** (`is_booked=False`) so it can be re-booked; a
  late cancel is *flagged*, never blocked (Rule #2).
- **No-show** is staff-only (nurse/doctor) and, unlike cancel, does **not** free
  the slot — a no-show still consumed the reserved time.
