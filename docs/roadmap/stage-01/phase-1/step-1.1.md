---
phase: 1
step: "1.1"
title: Auth data model & services
summary: users + sessions tables with Alembic migration, plus UserService and SessionService implementing the full auth logic (Argon2, hashed opaque tokens, constant-time login, session revocation) — no HTTP yet.
effort: 4
dependencies: ["0.2"]
agent: backend-dev
track: backend
---

# Step 1.1 — Auth data model & services

**Effort: 4** — two tables, one migration, and the two services that carry
all security-sensitive logic; no HTTP surface, so it verifies in isolation.

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) (binding contract — the DB
schema, validation rules, and backend conventions there are the spec for this
step). Runs in parallel with frontend step 1.2 — do not touch `frontend/`.

## Files

- Create `backend/app/db/models/user.py`, `backend/app/db/models/session.py`
- Create `backend/alembic/versions/<rev>_add_users_and_sessions.py`
- Create `backend/app/services/user_service.py`,
  `backend/app/services/session_service.py`
- Modify `backend/app/db/models/__init__.py` (import the models so Alembic
  autogenerate sees them)
- Modify `backend/pyproject.toml` (add `pwdlib[argon2]`)

## Implementation outline

- **Models** exactly per the shared-knowledge DB schema: ULID PKs via the
  existing `ULIDPrimaryKeyMixin`; `users.username String(32)` unique, stored
  lowercase; `users.role` as a **native PG enum** `user_role('user','admin')`
  with server default `'user'`; `sessions.token_hash String(64)` unique;
  `sessions.user_id` FK with `ON DELETE CASCADE` and an index; `expires_at`
  and `remember_me` per the pinned schema. Constraint/index names come from
  the existing naming convention — do not name them by hand.
- **Migration**: one Alembic revision on top of the pgvector baseline.
  Review the autogenerate output by hand: the enum must be created in
  `upgrade()` **and dropped in `downgrade()`** (autogenerate often misses the
  drop).
- **`UserService`** (owns its transactions; raises domain exceptions, no
  HTTP concepts):
  - `register(username, password) -> User` — normalize
    (`strip().lower()`), enforce uniqueness → raise `UsernameTakenError`;
    hash with pwdlib/Argon2 (`PasswordHash((Argon2Hasher(),))`).
  - `authenticate(username, password) -> User | None` — normalize, look up;
    when the user doesn't exist, verify against the module-level
    `_DUMMY_HASH` (constant-time behaviour) and still return `None`.
  - `set_role(username, role) -> User` — idempotent (already-target-role is
    success); revokes all sessions on **demotion admin → user** (via
    `SessionService`); raises `UserNotFoundError` for unknown users.
  - `reset_password(username, new_password) -> User` — rehash; revokes
    **all** sessions of that user; raises `UserNotFoundError`.
- **`SessionService`**:
  - `create_session(user_id, remember_me) -> tuple[str, Session]` — raw
    token from `secrets.token_urlsafe(32)`, stored only as its sha256 hex
    hash; `expires_at = now + (REMEMBER_ME_TTL if remember_me else SESSION_TTL)`
    (module constants: 30 days / 24 hours). Returns the raw token — it is
    never persisted.
  - `resolve_session(raw_token) -> User | None` — hash → lookup; lazily
    deletes an expired row and returns `None`; loads the user fresh (role
    changes apply to live sessions).
  - `revoke_by_token(raw_token)`, `revoke_all_for_user(user_id)`.
- **No sliding expiration** — `resolve_session` never extends `expires_at`.

## Out of scope (later steps)

- HTTP endpoints, cookies, CSRF, FastAPI dependencies → step 1.3.
- CLI commands → step 1.5. (Design `set_role`/`reset_password` so 1.5 only
  adds Typer plumbing.)
- Charset/length validation of username/password is the API layer's job
  (step 1.3 Pydantic) — the service only normalizes and enforces uniqueness.

## Verification

- `docker compose exec app-web alembic upgrade head` succeeds;
  `docker compose exec postgres psql -U <user> -d <db> -c '\d users' -c '\d sessions'`
  shows the pinned columns, the `user_role` enum, and the unique/FK indexes.
- `alembic downgrade -1 && alembic upgrade head` round-trips cleanly
  (proves the enum drop in `downgrade()`).
- Smoke via `docker compose exec app-web python -c "..."` (an `asyncio.run`
  one-off): register `"Alice "` → row stored as `alice`;
  `authenticate("ALICE ", pw)` returns the user; wrong password and unknown
  username both return `None`; `create_session` + `resolve_session`
  round-trip; `reset_password` leaves zero session rows for the user;
  `set_role` demotion also leaves zero session rows.

## Risks / notes

- Store only the token hash from day one — retrofitting later invalidates
  all sessions.
- Keep exceptions domain-level (`UsernameTakenError`, `UserNotFoundError`) —
  step 1.3 maps them to 409/404-style responses, step 1.5 to exit codes.
