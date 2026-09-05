# ADR-0006 — LLM as a system component: stub-default, opt-in real providers

- **Status:** Accepted
- **Date:** 2026-09-05
- **Related:** DESIGN §14; [business-rules.md](../domain/business-rules.md) Rule #11;
  [workflows/vitals-assistant.md](../workflows/vitals-assistant.md); ADR-0001 (no
  Docker, SQLite default), ADR-0004 (layered architecture), ADR-0005 (audit).

## Context
HealthyVytals gains its first AI-assisted feature: a **vitals triage assistant**
that turns recorded vitals into a short, structured, plain-language read for staff
(DESIGN §14, M12). A raw LLM call, used naively, is a poor fit for this codebase:
it returns free text of unpredictable shape (nothing downstream can rely on), it
is a network dependency that fails and rate-limits, and it is non-deterministic.
Dropping such a call directly into a service would violate the app's contracts,
reliability, and testability standards.

Two hard constraints shaped the decision:
1. **Local-first, zero-friction (ADR-0001).** The app and its full test suite must
   run on a fresh clone with **no API key and no vendor SDK installed**. A feature
   that requires a paid API to boot or to run tests is unacceptable.
2. **Layering and testability (ADR-0004).** AI must not leak vendor SDKs across the
   codebase or make the pure `domain/` layer impure, and every path must be
   unit-testable offline and deterministically.

## Decision
- **Treat the LLM as a system component**, not a chatbot. A single
  `core/llm/LLMClient` wraps the raw call in five disciplines: **output contracts**
  (validated Pydantic responses), **reliability** (retry with exponential backoff +
  jitter, transparent fallback model, per-request timeout), **determinism** (an
  input-hash cache for *effective* determinism), **routing** (a `triage`/`reasoning`
  tier selects a cheap/fast vs. capable model), and **observability** (one
  `CallRecord` per call). Cross-cutting infra ⇒ it lives in `core/llm`, like
  `core/security`.
- **The default provider is a deterministic offline STUB.** Same input → same
  output, no network, no SDK. It exercises every client path, so tests and demos
  are fully reproducible offline. **Real providers (`anthropic`, `openai`) are
  opt-in** via `HV_LLM_PROVIDER` + `HV_LLM_API_KEY`, and their SDKs are **imported
  lazily** only when selected. This is deliberately the *same shape* as the
  SQLite-default / Postgres-opt-in choice in ADR-0001.
- **The deterministic rule stays the source of truth.** For the vitals assistant,
  `domain/vitals_ranges.flag_out_of_range` (Rule #5, pure, unit-tested) computes the
  authoritative flags; the model is asked to *explain and prioritize* them, never to
  set thresholds. A safety clamp prevents the model downgrading a flagged reading to
  "routine".
- **Decision-support, human-in-the-loop — never diagnosis.** Output is advisory for
  a clinician who decides (honors the Non-Goals). On any LLM failure/refusal the
  service **degrades safely** to a rules-only assessment rather than failing.
- **AI use is audited (ADR-0005).** Each invocation records an `llm.*` action, with a
  distinct `…_degraded` action when the fallback path was taken.

## Consequences
**Positive:** every service gets contracts/reliability/observability for free from
one client; the app stays local-first and 100% testable offline; swapping vendors
(or none) is a config change; the AI can never silently override a clinical rule;
AI use is as accountable as any other PHI touch.
**Negative / mitigations:** the stub is not a real model, so it validates *plumbing*,
not answer quality — real-model output quality is evaluated separately (the book's
evaluation chapter, future M-Eval). The lazy-import indirection costs a little
clarity; we mitigate with a clear `ProviderError` when an opted-in SDK is missing.

## Alternatives considered
- **Call a vendor SDK directly from the service.** Rejected: leaks the vendor across
  layers, needs an API key to run tests, and re-implements retries/caching per call
  site.
- **Overload the audit trail as the observability sink (ADR-0005).** Rejected:
  `AuditLog` records PHI/security *actions* for compliance and has no
  token/latency/metadata fields. LLM telemetry is operational; it goes to a logging
  `CallRecord`. A service that needs both emits both.
- **Require a real API key (no stub).** Rejected: breaks ADR-0001's fresh-clone,
  no-Docker, one-command promise and makes tests non-deterministic and costly.
- **Let the model compute vitals ranges.** Rejected on safety: a validated,
  age-banded clinical rule (Rule #5) must not be replaced by a non-deterministic
  model; the model explains the rule's output, it does not supersede it.
