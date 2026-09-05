# Web UI map — role screens (server-rendered Jinja2 + HTMX)

The browser UI is served by the same FastAPI app as the JSON API (DESIGN §7.3),
styled with vendored **Pico.css** + an app-shell (`dashboard/_base.html`) that
renders a **role-aware sidebar**. Every web route is a thin controller over the
same services the API uses (rule §7.6.7) — no business logic in templates.

## Shell & auth
- `base.html` — public document shell (landing, login, register).
- `dashboard/_base.html` — authenticated app shell: sidebar nav (per-role link
  map) + content; role badge + logout in the sidebar foot.
- Auth: cookie session (`hv_access`), resolved by `web/deps.require_web_user`
  (redirects to `/login` when anonymous). Fine role checks live in each route.

## Screens by role

| Role | Route(s) | What it does |
|---|---|---|
| **Patient** | `/dashboard` | Overview: upcoming-appt / active-rx / total metrics + quick actions |
| | `/appointments/book`, `/appointments/mine` | Book an open slot (HTMX), list own appointments |
| | `/clinical/history`, `/clinical/prescriptions` | Own encounters (vitals+diagnoses), own prescriptions |
| **Nurse** | `/dashboard` | Ward board: today's appointments + metrics |
| | `POST /clinical/appointments/{id}/check-in` | Advance appointment to checked-in |
| | `/clinical/appointments/{id}/vitals` | Triage vitals-entry form (HTMX) → age-flagged result; auto-creates the encounter |
| **Doctor** | `/dashboard` | Worklist: scheduled appointments + treated-patient count |
| | `POST /clinical/appointments/{id}/open` | Open/resume the encounter, go to it |
| | `/clinical/encounters/{id}` | Review vitals, add diagnosis (HTMX), prescribe (safety-checked, HTMX) |
| **Admin** | `/dashboard` | Overview: per-role user counts + quick links |
| | `/admin/users` | List accounts; provision staff; activate/deactivate |
| | `/admin/audit` | Filterable audit-log viewer (PHI/security actions) |

## Conventions
- **HTMX partials** live under `templates/**/partials/` and are swapped into a
  target element (booking result, diagnoses list, prescriptions list, vitals
  result). Full pages extend the shell; partials render only the fragment.
- **Authorization mirrors the API:** coarse role gate in the route (`require_web_user`
  + a role check), fine ownership/treating-relationship checks in the service.
- **No Node/build step** — Pico.css and htmx.min.js are vendored static files.

Route tests: `tests/web/` (per-feature + `test_web_routes_sweep.py` covering
public render, protected→login redirects, role gating, and static assets).
