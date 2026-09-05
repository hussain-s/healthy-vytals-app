# Workflow — Vitals trend charts (§15, M13)

How a patient's recorded vitals become a line chart over time on the medical-history
page. See [business-rules.md](../domain/business-rules.md) Rule #12 and
[ADR-0007](../adr/ADR-0007-client-charting-vendored-chartjs.md).

## Sequence

```mermaid
sequenceDiagram
    actor Patient
    participant Page as web/clinical (history page)
    participant Browser as Chart.js (vendored)
    participant API as api/v1/patients
    participant Svc as clinical_service
    participant Repo as encounter_repository
    participant DB as SQLite

    Patient->>Page: GET /clinical/history
    Page-->>Patient: HTML (raw vitals listed) + <canvas> + Chart.js <script>
    Browser->>API: GET /api/v1/patients/{id}/vitals-series (fetch)
    API->>Svc: get_vitals_series(viewer, patient_id)
    Svc->>Repo: has_treating_relationship? (doctors only)
    alt viewer may not read this patient
        Svc->>DB: audit vitals_series.read_denied (committed)
        API-->>Browser: 403
        Browser->>Page: show empty-state note (raw vitals stay visible)
    else allowed
        Svc->>DB: audit vitals_series.read
        Svc->>Repo: vitals_for_patient (+ consent filter §5.8)
        Repo-->>Svc: time-ordered points
        API-->>Browser: VitalsSeriesOut (JSON)
        Browser->>Page: render line chart (≥2 points) or empty-state
    end
```

## Why it is shaped this way
- **Same read rule as history (Rule #12).** A chart is another PHI read; it reuses
  `can_view_patient_history` + the §5.8 consent gate, so it can never expose more
  than the history page beside it. Audited like any history read (Rule #7).
- **Server owns the data; the library only draws (ADR-0007).** Authorization,
  scoping, and clinical meaning are server-side; Chart.js just renders the JSON.
- **Progressive enhancement.** The raw vitals are listed server-side, so a blocked
  script, a fetch error, or < 2 data points degrades to an empty-state note — never
  a blank page and never hidden clinical data.
- **No build step.** Chart.js is vendored as one static file (like HTMX/Pico),
  loaded only on charting pages via the base template's `head_extra` block.

## Entry points
- **API:** `GET /api/v1/patients/{patient_id}/vitals-series` → `VitalsSeriesOut`
  (nurse/treating-doctor/own-patient; admin denied).
- **Web:** the medical-history page (`web-my-history`) renders the chart canvas +
  the vendored `chart.umd.min.js`.
