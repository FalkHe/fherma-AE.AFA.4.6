---
phase: 2
step: "2.4"
title: SSE client hook
summary: useServerEvents over native EventSource mapping the pinned event names to TanStack Query invalidations, plus useServerEventsStatus and the pinned query-key module — real code, no stub; a dead /api/events just retries silently.
effort: 2
dependencies: ["1.6"]
agent: frontend-dev
track: frontend
---

# Step 2.4 — SSE client hook

**Effort: 2** — one hook, one key module, one mount point; the backend
endpoint (2.7) does not need to exist yet.

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *SSE / LISTEN-NOTIFY* (event
names, payload shapes, the invalidation map, the binding hook requirements)
and *Frontend conventions* (query keys, `frontend/src/queryKeys.ts`).
[`ui-spec.md`](ui-spec.md) §3.3. Phase-1 shared-knowledge for the
`queryClient.ts` location. Zero deviations; stop and report if one seems
necessary.

## Files

- Create `frontend/src/hooks/useServerEvents.ts`
- Create `frontend/src/hooks/useServerEvents.test.ts`
- Create `frontend/src/queryKeys.ts` (the pinned key builders)
- Modify `frontend/src/components/AppLayout.tsx` (mount once when
  `useAuth().user` exists)

## Implementation outline

- Native `EventSource("/api/events")` (cookie auth is automatic; no
  fetch-event-source). Listen for the three pinned event names; each →
  prefix invalidation per the pinned map via the shared `queryClient`.
- `useServerEventsStatus(): {connected: boolean}` — module-level state +
  `useSyncExternalStore`, so layouts render connection warnings without
  owning the `EventSource`.
- On reconnect (`open` after any `error`): blanket-invalidate `["products"]`
  + `["operations"]` (gap events are lost). Native retry only — **no custom
  backoff, no polling**.
- Mount exactly once in the authenticated shell (`AppLayout`, gated on
  `user`); unmount closes the connection (logout must not leak a stream).

## Out of scope

- The disconnect warning Alert in `AdminLayout` (rendered in 2.8), the
  backend endpoint (2.7).

## Verification

- `pnpm typecheck && pnpm test` green (tests mock `EventSource`: event →
  correct invalidation; error→open → blanket invalidation; unmount closes).
- With the backend down, the app renders normally — no console error loop.

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*.
