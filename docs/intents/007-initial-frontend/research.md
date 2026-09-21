---
author: fhit:architect
owner: agent
created: 2026-09-19
updated: 2026-09-19
---
# Research: 007 Initial Frontend

## Facts

**Frontend today** — React 19.2.8, MUI 9.4.0, TanStack Query 5.102.8, React
Router 8.3.1, react-i18next, `openapi-fetch` (`frontend/pnpm-lock.yaml`). No
second UI/styling library; no icon package (forbidden by
`frontend/src/structure.test.ts:78`). Modules `auth` and `home`; routes `/`,
`/signin`, `/signup` with per-route `RequireAuth`/`RequireAnonymous`
(`frontend/src/App.tsx:13-39`). One network file, owning the CSRF token in
module memory (`frontend/src/core/api/client.ts:11-32`); one hook per
operation; server state only in Query. Tests drive one fetch dispatcher
(`frontend/src/test/network.ts:50`).

Three existing constraints this intent collides with:
- `frontend/src/api/schema.d.ts` is **stale**: it carries health, auth and
  users paths only (lines 7, 24, 41, 58, 75) — no playthrough. `make
  generate-api` must run before any run-related hook is typed.
- `structure.test.ts:109` pins `core/` to an exact file list and forbids
  `.tsx` there; `:132` forbids `src/components/`. A new i18n namespace and any
  shared layout component require editing that test.
- `AppShell` lives in `home` and, per `frontend/src/modules/home/README.md`,
  "graduates unchanged once a second module renders it".
  `useSignIn.ts:3` records that the first extra protected route must flip its
  cache-then-navigate order to navigate-then-write.

**Backend surface** (`backend/app/api/v1/router.py`): health, auth, users,
playthrough — **content is not mounted and has no `routes.py`**. Auth is a
HttpOnly `session` cookie plus an `X-CSRF-Token` header on writes
(`auth/dependencies.py:21-47`); no bearer token, no refresh endpoint;
`GET /users/me` re-issues the CSRF token (`users/routes.py:10-13`). Six
playthrough endpoints (`playthrough/routes.py:19-113`): create run from
`{campaignId}`, list runs, read one run, create character, rename, archive.
A run reads as `id, campaignId, contentVersion, title, status, createdAt`
only (`playthrough/schemas.py:13-22`); the list returns every run the caller
is a member of, archived included, newest first (`service.py:179-190`).
Campaign/adventure titles live in JSON content
(`content/schemas.py:118,138`; `backend/content/campaigns/greenhollow/v1/`),
reachable only through `content.service.list_campaign_ids()` /
`load_campaign()` (`content/service.py:51,73`) — no HTTP.

**Gaps between wish and backend, precisely:**
1. *Campaign catalogue* — no endpoint lists available campaigns or their
   titles/summaries. The select dialog and every run label have nothing to
   read (a run carries `campaignId`, never a title).
2. *Participated runs* — the concept does not exist: `role IN ('owner')` and
   one member per run (`playthrough/models.py:59-62`), no invite or join path.
   Every listed run is the caller's own.
3. *Players list* — no endpoint returns a run's members or their character.
   `POST …/character` returns a character, but nothing reads one back. "Ready"
   is only derivable from the run's `status`: `create_character` is the sole
   `setup → ready` transition (`service.py:300`).
4. *Adventures* — `adventure_runs` exists as a table and is referenced by no
   service and no route; the campaign's adventure list is content-only. So
   neither the adventure list nor its status is reachable.
5. *Start* — `POST …/campaign/{id}/adventure` is decided (005-D3) but unbuilt;
   005 sprints 05/06 are still `open`. `activate_campaign_run` exists with no
   route (`service.py:349`). The Start CTA has nothing to call.
6. Dashboard filtering (hide archived / `setup`) has no query parameter;
   client-side filtering over the existing list is enough.

MUI 9 `Dialog` covers the select dialog; v9 moved `PaperProps`/
`TransitionComponent` to `slots`/`slotProps` (@mui/material 9.4.0 — source:
context7, docs v9.2.0).

## Options

| Option | Pro | Con |
|---|---|---|
| **A** Frontend only: hard-code the one campaign, derive everything from run `status` | No backend work; ships in ~2 sprints | Campaign copy duplicated in the UI; players list is "me"; adventure list is invented client-side — rewritten as soon as the backend lands |
| **B** Add two read-only endpoints: campaign catalogue + one run overview (players, adventures, statuses) | The screen reads real state; the UI never invents domain data; small, additive, no migration | Backend work inside a frontend intent (~1 sprint); overview joins content + playthrough |
| **C** B plus building adventure entry (`enter_adventure`) so Start works | Whole wish delivered | Pulls in 005-05/06 (events, SSE, placement) — several sprints, and there is no play screen to land on |
| **D** Defer the run screen entirely; ship auth + dashboard only | Smallest | Drops half the wish |

Recommendation: **B** — add `GET /api/v1/content/campaigns` (id, title,
summary) and one `GET /api/v1/playthrough/campaign/{runId}/overview`
returning the run, its players with a ready flag, and its adventures with
status; the Start CTA exists and stays disabled, its wiring deferred to the
adventure-entry intent. Trade-off: one backend sprint in a frontend intent,
against a UI that would otherwise hold invented content. Failure behaviour:
both are reads, so a failure is a retryable error panel; blast radius stays
inside the playthrough module plus the new content route.

Sub-choices: **one aggregate overview call, not three** — one loading state,
one place that joins content to run rows, no client-side join. **Guards: one
layout route** (`<Route element={<RequireAuth><Outlet/></RequireAuth>}>`)
wrapping `/` and `/runs/:runId`, instead of repeating the guard per route.
**New frontend module `playthrough`**, mirroring the backend; `AppShell`
promoted to a shared location (the pinned `core/` list in `structure.test.ts`
must be relaxed to allow it and the new i18n namespace).

## Open questions

**Product-visible (need decisions):**
- Own vs participated: show one list, or two sections one of which is always
  empty until sharing exists?
- Do archived and never-started runs appear on the dashboard?
- What is a run called in the list — campaign title, the player's own title
  (nullable, no rename UI), the start date?
- What does the "Create Character" button do in this intent: nothing,
  "coming soon", or actually create the seed character (which would make the
  run ready and enable Start)?
- What happens after "Start" while no play screen exists?
- Anonymous visitor lands on sign-in or sign-up?
- Empty dashboard: what does a user with no runs see?
- A run whose campaign content is gone or renamed — what is shown?
- Starting the same campaign twice is allowed by the backend: warn, block or
  ignore?

**Technical (agent's call):** exact overview payload, query keys and
invalidation, module and route naming, how the pinned structure test is
relaxed, whether archived runs are filtered client-side.
