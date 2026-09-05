# API — contract notes

The full machine-readable contract is exported to
[`openapi.json`](openapi.json) (regenerate any time — see below). This page adds
the *conventions* that the raw schema doesn't spell out.

## Surface
- All JSON endpoints are versioned under **`/api/v1`**. The server-rendered web UI
  (HTML/HTMX) lives at unversioned paths (`/`, `/login`, `/dashboard`,
  `/clinical/...`) and is excluded from the OpenAPI schema.
- Interactive docs (dev only): `http://localhost:8000/docs`.

## Conventions
- **Auth:** `POST /api/v1/auth/login` returns `{access_token, refresh_token,
  token_type: "bearer"}`. Send `Authorization: Bearer <access>` on protected
  endpoints. The browser UI uses an HttpOnly `hv_access` cookie instead; both
  resolve to the same user.
- **Errors:** every failure returns the standard envelope
  `{code, message, details?}` with a **stable `code`** (e.g. `not_found`,
  `permission_denied`, `slot_conflict`, `illegal_transition`, `unsafe_prescription`).
  Clients branch on `code`, not prose. Request-validation failures use
  `request_validation_error` with field details.
- **Pagination:** list envelopes use `Page[T]` = `{items, total, limit, offset}`.
- **Status codes:** 201 create · 200 read/action · 401 unauthenticated ·
  403 forbidden (role/ownership) · 404 not found · 409 conflict (state/safety) ·
  422 malformed input.

## Key error codes by domain
| Code | HTTP | Meaning |
|---|---|---|
| `invalid_credentials` | 401 | login/refresh failed (uniform for unknown email / wrong password) |
| `email_already_registered` | 409 | duplicate registration |
| `staff_role_required` | 409 | admin provisioning got the PATIENT role |
| `slot_conflict` | 409 | slot taken / buffer conflict (§5.2) |
| `illegal_transition` | 409 | illegal appointment state change or wrong role (§5.1) |
| `unsafe_prescription` | 409 | blocked by §5.4 (`details.reason` = allergy/interaction/refill_cap) |
| `permission_denied` | 403 | role or ownership/treating-relationship check failed |

## Regenerating the export
```bash
cd backend
../.venv/bin/python -c "import json; from app.main import create_app; \
  json.dump(create_app().openapi(), open('../docs/knowledge-base/api/openapi.json','w'), indent=2, sort_keys=True)"
```
Keep the export in sync when endpoints change (Phase 6 traceability check).
