---
phase: 2
step: "2.7"
title: SSE endpoint & LISTEN fan-out
summary: A per-process psycopg LISTEN loop on a dedicated auto-reconnecting connection (started in the FastAPI lifespan) fanning app_events payloads to cookie-authenticated GET /api/events via sse-starlette. Merging this step is cross-track sync point S1.
effort: 3
dependencies: ["2.6"]
agent: backend-dev
track: backend
---

# Step 2.7 — SSE endpoint & LISTEN fan-out

**Effort: 3** — one listener loop with careful connection lifecycle, one
endpoint. **Merging this step unblocks frontend step 2.15 (sync point S1) —
the OpenAPI schema then contains 2.3 + 2.6.**

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *SSE / LISTEN-NOTIFY* section
is the spec (channel, event/data framing, ping interval, cookie auth).
`docs/architecture.md` → *Chat / Realtime*. The listener uses a dedicated
long-lived psycopg connection with reconnect logic — **never a pooled
session** (Phase-0/1 engine pitfalls in `docs/qa-checklist.md`). Zero
deviations; stop and report if one seems necessary.

## Files

- Create `backend/app/services/notification_listener.py`
- Create `backend/app/api/endpoints/events.py`
- Create `backend/tests/services/test_notification_listener.py`
- Modify `backend/app/main.py` (lifespan start/stop; router mount)

## Implementation outline

- `notification_listener.py`: one background task per web process — dedicated
  psycopg async connection, `LISTEN app_events`, fan-in payloads to an
  in-process registry of subscriber queues; reconnect with backoff on
  connection loss; clean shutdown in lifespan teardown.
- `GET /api/events`: sse-starlette `EventSourceResponse`,
  `Depends(current_user)` (session cookie — plain endpoint, not JSON:API).
  Each payload → SSE `event:` = pinned event name, `data:` = payload JSON;
  ping every 15 s; subscriber queue removed on disconnect.
- `/health` and `/ready` remain outside auth and unaffected by a dead
  listener (broker/listener outage must not make the HTTP app unready).

## Verification

- `make backend-test` green (listener fan-out and cleanup tested with a
  stubbed connection; endpoint auth 401 without cookie).
- Manual: `curl -N -b cookiejar http://localhost:8000/api/events` streams
  `operation.updated` events while `app operations demo` runs in parallel;
  killing postgres briefly → listener reconnects, stream resumes.

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*, and **announce S1 is open** in the step report.
