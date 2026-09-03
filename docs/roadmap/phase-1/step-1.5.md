---
phase: 1
step: "1.5"
title: CLI user commands & bootstrap docs
summary: app users set-role and app users reset-password Typer commands over the existing services — the first-admin bootstrap path — plus the README one-liner.
effort: 2
dependencies: ["1.3"]
agent: backend-dev
track: backend
---

# Step 1.5 — CLI user commands & bootstrap docs

**Effort: 2** — two thin Typer commands over the already-built services; the
only work is CLI plumbing following the pinned async pattern. (Implementation
only needs step 1.1; the dependency on 1.3 is for the end-to-end
verification via `/auth/me`.)

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — especially the *CLI async
pattern* and session-revocation rules under *Backend conventions*.

## Files

- Create `backend/app/cli/users.py`
- Modify `backend/app/cli/main.py` —
  `app.add_typer(users.app, name="users")`, matching the existing
  `openapi` sub-app registration
- Modify `README.md` — bootstrap one-liner:
  `docker compose exec app-web app users set-role <name> admin`
  *(docs-writer)*

## Implementation outline

- **`app users set-role <username> <user|admin>`**: role as a `str`-based
  `Enum` argument; calls `UserService.set_role` via the pinned CLI async
  pattern (sync Typer body → `asyncio.run(_impl(...))` → session from the
  sessionmaker → service call). Idempotent success → exit 0; unknown user →
  stderr message, exit 1. Demotion revokes sessions — that logic lives in
  the service (step 1.1); **verify it's there, don't reimplement**.
- **`app users reset-password <username>`**: password via
  `typer.prompt(..., hide_input=True, confirmation_prompt=True)` — never a
  CLI argument (shell history). Calls `UserService.reset_password` (which
  revokes all sessions). Same exit-code convention.
- Username lookup is case-insensitive because the service normalizes — pass
  input through unchanged.
- **No SQL in the CLI layer.** This file is the reference implementation of
  the CLI async pattern for every later command (re-embed, etc.) — keep it
  exemplary.

## Verification

- Register + login via curl (per step 1.3's checks), keep the cookie jar.
- `docker compose exec app-web app users set-role alice admin` → exit 0;
  `GET /auth/me` with the **existing** cookie now returns `"role":"admin"`
  (proves role is read from the DB per request, not cached in the session
  row).
- Re-run the same `set-role` → exit 0 (idempotent).
  `app users set-role ghost admin` → exit 1, message on stderr.
- `app users reset-password alice` (prompted twice, hidden): the old cookie
  → `/auth/me` 401 (sessions revoked); old-password login → 401;
  new-password login → 200.
- README contains the bootstrap one-liner.

## Risks / notes

- If `UserService.set_role`/`reset_password` are missing or don't revoke
  sessions as pinned, that is a step-1.1 defect — fix it there (service
  layer), not by adding logic to the CLI.
