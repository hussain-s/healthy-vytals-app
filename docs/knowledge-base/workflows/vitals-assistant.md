# Workflow — AI vitals triage assistant (§14, M12)

How a set of recorded vitals becomes a structured, advisory `VitalsAssessment`,
and how the deterministic clinical rule stays in charge of the model. See
[business-rules.md](../domain/business-rules.md) Rule #11 and
[ADR-0006](../adr/ADR-0006-llm-component-layer.md).

## Sequence

```mermaid
sequenceDiagram
    actor Nurse
    participant Svc as services/vitals_assistant_service
    participant Dom as domain/vitals_ranges (Rule #5, pure)
    participant LLM as core/llm/LLMClient
    participant Prov as provider (stub | anthropic | openai)
    participant DB as SQLite (audit)

    Nurse->>Svc: assess_vitals(age, reading)
    Svc->>Dom: flag_out_of_range(age, reading)
    Dom-->>Svc: authoritative flags (ground truth)
    Svc->>LLM: analyze(content+flags, VitalsAssessment, tier=reasoning)
    LLM->>Prov: complete(...)  %% retry+jitter, timeout, cache, fallback
    alt provider returns valid JSON
        Prov-->>LLM: text
        LLM-->>Svc: validated VitalsAssessment
        Svc->>Svc: safety clamp (flag present ⇒ never "routine")
        Svc->>DB: audit llm.vitals_assessed
    else refusal / error / invalid after retries
        LLM-->>Svc: LLMError / LLMRefusal
        Svc->>Svc: degrade → rules-only assessment (from flags)
        Svc->>DB: audit llm.vitals_assessed_degraded
    end
    Svc-->>Nurse: VitalsAssessment (advisory; a clinician decides)
```

## Why it is shaped this way
- **The rule leads, the model explains.** `flag_out_of_range` is computed first and
  passed into the prompt; the model prioritizes those flags in plain language but
  cannot set thresholds or contradict them. Safety-critical behavior stays
  deterministic and unit-tested (Rule #5), while staff get a readable summary.
- **The system is dependable even though the model isn't.** Reliability (retry +
  jitter, timeout, fallback), effective determinism (input-hash cache), routing,
  and observability all come from `core/llm/LLMClient` — the five disciplines.
- **It never hard-fails and never over-reassures.** On model trouble it degrades to
  a rules-only assessment; if a real flag exists it can never read "routine".
- **Offline by default.** The stub provider serves a schema-valid response with no
  API key or SDK, so this flow runs on a fresh clone (ADR-0006).

## Entry points (M12 exposure slice, c074)
- **API:** `POST /api/v1/encounters/{encounter_id}/vitals-assessment` — nurse or
  treating doctor; returns `VitalsAssessmentOut`. Coarse role gate on the router;
  the treating-relationship check + audit are in the service.
- **Web (nurse):** after recording vitals, a "Get AI triage assist" button
  (`web-vitals-assessment`) fetches the assessment as an HTMX partial rendered into
  the vitals page. Nurse-only; requires vitals to have been recorded first.
- Both resolve the encounter's patient age + latest reading, then call
  `assess_encounter_vitals`.

## Configuration
- `HV_LLM_PROVIDER` — `stub` (default), `anthropic`, or `openai`.
- `HV_LLM_API_KEY`, `HV_LLM_MODEL_REASONING`, `HV_LLM_MODEL_TRIAGE`,
  `HV_LLM_FALLBACK_MODEL`, `HV_LLM_TIMEOUT_S`, `HV_LLM_MAX_RETRIES`,
  `HV_LLM_CACHE_ENABLED` — see `.env.example`.

> **Not diagnosis.** The assessment is decision-support for a clinician who decides
> (DESIGN Non-Goals; §14.1).
