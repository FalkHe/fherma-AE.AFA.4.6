---
phase: 1
step: "1.3"
title: Auth endpoints, cookies & CSRF
summary: The four /auth/* endpoints with the pinned cookie/CSRF behaviour, plus current_user, current_admin and csrf_protect dependencies — the step that freezes the OpenAPI surface for the frontend.
effort: 4
dependencies: ["1.1"]
agent: backend-dev
track: backend
---

# Step 1.3 — Auth endpoints, cookies & CSRF

**Effort: 4** — four endpoints over existing services plus the cookie/CSRF
machinery and the three dependencies every later router reuses.

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — the *Auth API contract*,
*Cookies & CSRF*, *Validation rules*, and *Backend conventions* sections are
the spec for this step, field by field. **This step's OpenAPI output is
consumed verbatim by frontend step 1.6 — any deviation from the pinned
contract breaks the cross-track sync point. Treat the contract as the spec,
not a suggestion; if it cannot be met, stop and report.**

## Files

- Create `backend/app/api/schemas/auth.py`
- Create `backend/app/api/endpoints/auth.py`
- Create `backend/app/api/deps.py`
- Modify `backend/app/main.py` (include the auth router at `/auth`),
  `backend/app/api/schemas/__init__.py`,
  `backend/app/api/endpoints/__init__.py`

## Implementation outline

- **Schemas** (`schemas/auth.py`): `RegisterRequest`, `LoginRequest`
  (`remember_me` with camelCase alias, default `False`), `UserResponse`
  (`id`, `username`, `role`). Use `alias_generator=to_camel,
  populate_by_name=True`. Username/password constraints as field validators
  (username: strip/lower then 3–32 + `^[a-z0-9_.-]+$`; password: 8–128) so
  422s carry field locations.
- **Endpoints** (`endpoints/auth.py`) exactly per the pinned contract table:
  - `POST /auth/register` → 201 + `UserResponse`; `UsernameTakenError` →
    409 `{"detail": "Username is already taken."}`. **No session created.**
  - `POST /auth/login` → authenticate (constant-time path is in the
    service); failure → 401 `{"detail": "Invalid username or password."}`;
    success → create session, set **both** cookies exactly per the pinned
    attributes (session: HttpOnly, SameSite=Lax, Path=/, Secure iff
    production, Max-Age=2592000 only with rememberMe; csrf_token: same but
    **not** HttpOnly, fresh `secrets.token_urlsafe(32)` per login) → 200 +
    `UserResponse`.
  - `POST /auth/logout` → `Depends(current_user)` + `Depends(csrf_protect)`;
    revoke the session row; clear both cookies (`Max-Age=0`); 204.
  - `GET /auth/me` → `Depends(current_user)` → 200 + `UserResponse`.
- **Dependencies** (`api/deps.py`):
  - `current_user` — reads the `session` cookie, resolves via
    `SessionService.resolve_session` → 401
    `{"detail": "Not authenticated."}` when absent/invalid/expired. Loads
    the user fresh from the DB (role changes apply to live sessions).
    Docstring: this is the **default guard for all future `/api/*` routers**;
    `/health` and `/ready` stay outside it.
  - `current_admin` — `Depends(current_user)`; 403
    `{"detail": "Admin privileges required."}` when `role != "admin"`.
    Ships now so Phase-2 routers just import it.
  - `csrf_protect` — double-submit check per the pinned pattern
    (`secrets.compare_digest` of `X-CSRF-Token` header vs `csrf_token`
    cookie; 403 `{"detail": "CSRF token missing or invalid."}`).

## Out of scope (later steps)

- CLI commands → 1.5. Frontend anything → 1.4/1.6.
- No sliding expiration, no session-management endpoints, no rate limiting
  (explicitly out of scope per `docs/general/architecture.md`).

## Verification (curl, with `-c jar -b jar` for cookies)

- `POST /auth/register {"username":"Alice","password":"secret123"}` → 201,
  body has `"username":"alice"`; repeat → 409; 7-char password → 422.
- `POST /auth/login` with `"rememberMe":true` → 200; `Set-Cookie` shows
  `session` with `HttpOnly; SameSite=Lax; Max-Age=2592000` and a readable
  `csrf_token`; without `rememberMe` → no `Max-Age` on either cookie.
- `GET /auth/me` with the cookie jar → 200 with `"role":"user"`; without
  cookies → 401.
- `POST /auth/logout` without `X-CSRF-Token` → 403; with the matching header
  → 204; subsequent `GET /auth/me` → 401. Wrong-password login → 401.
- `GET /health` still returns 200 without any cookies.
- `docker compose exec app-web app openapi export | jq '.paths | keys'`
  lists all four `/auth/*` paths — **this unblocks frontend step 1.6**.

## Risks / notes

- Cookie clearing must repeat the same Path/SameSite attributes used when
  setting, or browsers keep the stale cookie.
- Map service exceptions to responses in the endpoint layer — the services
  (1.1) stay HTTP-free.
