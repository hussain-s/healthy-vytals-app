# Workflow — Registration & login (stories A1–A4)

How accounts are created and how sessions are established, across both the JSON
API and the server-rendered UI. See
[ADR-0003](../adr/ADR-0003-authentication-and-authorization.md).

## Sequence

```mermaid
sequenceDiagram
    actor Visitor
    actor Admin
    participant API as api/v1/auth + users
    participant Svc as auth_service
    participant DB as SQLite

    Note over Visitor,DB: Patient self-registration (A1)
    Visitor->>API: POST /auth/register {email, password}
    API->>Svc: register_patient(...)
    Svc->>DB: create User(PATIENT) + PatientProfile, audit user.register
    API-->>Visitor: 201 UserOut (no password hash)

    Note over Admin,DB: Staff provisioning (A2) — not self-service
    Admin->>API: POST /users {email, password, role}  [Bearer admin]
    API->>Svc: provision_staff(admin_id, ...)
    Svc->>DB: create User(role) + role profile, audit user.provision
    API-->>Admin: 201 UserOut

    Note over Visitor,DB: Login (A3) + refresh (A4)
    Visitor->>API: POST /auth/login {email, password}
    API->>Svc: login(...)
    alt bad credentials / inactive
        Svc->>DB: audit auth.login_failed (committed)
        API-->>Visitor: 401 invalid_credentials (uniform)
    else ok
        Svc->>DB: audit auth.login
        API-->>Visitor: 200 {access_token, refresh_token}
    end
    Visitor->>API: POST /auth/refresh {refresh_token}
    API->>Svc: refresh_tokens(...) (rejects access-as-refresh)
    API-->>Visitor: 200 {new access, new refresh}
```

## Notes
- **Only patients self-register;** staff are admin-provisioned with an explicit
  role (a PATIENT role is rejected). Mirrors a real clinic.
- **Uniform failure:** unknown email and wrong password return the *same* 401, so
  the API doesn't reveal which emails exist. Deactivated accounts also fail here.
- **Two transports, one identity:** the API uses `Authorization: Bearer`; the web
  UI carries the access token in an HttpOnly `hv_access` cookie set at
  `POST /login`. Both resolve via `get_current_user`.
- **Token types are enforced:** an access token can't be used where a refresh is
  required, or vice versa.
- Every outcome — including failures — is audited (§5.7).
