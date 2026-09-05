# ADR-0007 — Client-side charting via a vendored Chart.js (no build step)

- **Status:** Accepted
- **Date:** 2026-09-05
- **Related:** DESIGN §13 (M10 vitals trends), §7.3 (server-rendered UI), ADR-0001
  (no Docker / no Node build step); [business-rules.md](../domain/business-rules.md)
  Rule #5 (vitals ranges) & Rule #12 (vitals trends);
  [workflows/vitals-trends.md](../workflows/vitals-trends.md).

## Context
Milestone M10 adds **vitals trend charts** so a patient/clinician can see a
measurement (heart rate, SpO₂, …) move over time. DESIGN §13.2 originally sketched
these as *server-rendered inline SVG* to avoid a JS build. In practice we want real
interactivity — hover tooltips, multiple series, legends, sensible axis handling —
which hand-rolled SVG makes tedious and fragile. The constraint that actually
matters (ADR-0001) is **"no Node/JS build step"**, not "no JavaScript": the app
already ships behavior with **HTMX** and already **vendors** third-party front-end
assets as single static files (`htmx.min.js`, `pico.min.css`).

## Decision
- **Use [Chart.js] for client-side charts, vendored as one static file**
  (`app/web/static/chart.umd.min.js`, the UMD build, v4.4.x), served like
  `htmx.min.js`. No npm, no bundler, no build — it is a `<script>` tag, honoring
  ADR-0001's real intent.
- **The server owns the data, not the rendering.** A scoped JSON endpoint
  (`/api/v1/patients/{id}/vitals-series`) returns the time series; a tiny inline
  init script hands that data to Chart.js. All authorization, scoping, and the
  clinical meaning stay server-side; the library only draws.
- **Progressive enhancement.** The history page is useful without the chart (the
  raw vitals are already listed); the chart is an addition, so a failed/blocked
  script never hides clinical data.
- **Pinned + offline.** The vendored file is committed and version-pinned, so a
  fresh clone renders charts with no network and no install — same guarantee as the
  rest of the stack (ADR-0001, ADR-0006).

## Consequences
**Positive:** rich, familiar charts with little code; no toolchain; works offline;
consistent with how HTMX/Pico are already handled; the data endpoint is reusable
(API clients, future dashboards).
**Negative / mitigations:** a ~200 KB static asset (comparable to the vendored
Pico CSS) — acceptable for a local-first teaching app, and loaded only on pages
that chart; one more vendored dependency to update by hand (documented here and in
the runbook). It is client-side JS, a step beyond "HTMX only" — bounded by loading
it *only* where a chart renders and keeping all data/authorization server-side.

## Alternatives considered
- **Hand-rolled inline SVG (the original §13.2 sketch).** Rejected for real charts:
  axes, multi-series, tooltips, and responsive sizing become significant bespoke
  code to build and maintain. Kept as the fallback idea for a trivial sparkline.
- **A charting library via npm/a bundler.** Rejected: violates ADR-0001's no-build
  rule outright.
- **A server-side image (matplotlib → PNG).** Rejected: adds a heavy Python imaging
  dependency and loses interactivity; harder to theme with the app.
