---
author: fhit:architect
owner: agent
created: 2026-09-22
---
# Research: sprint 007/09 — start a campaign dialog

## Facts

**Backend is complete; no backend work.**
- `POST /api/v1/playthrough/campaign` → 201 `CampaignRunRead`; body `StartCampaignRunRequest`
  (`backend/app/modules/playthrough/routes.py:30-47`, `schemas.py:11-25`). Guarded by `CsrfAuth`.
- Repeat starts are explicitly allowed — two starts of the same campaign yield two distinct runs; the unique
  constraint is per-run, not per-user (`service.py:188-232`, comment at `:220-229`). AC3 needs nothing.
- `GET /api/v1/content/campaigns` → `CampaignSummaryRead[]` = `{id, title, summary, adventureCount}`
  (`backend/app/modules/content/routes.py:11-21`, `content/schemas.py:152-156`). No frontend code reads it yet
  (`grep content/campaigns frontend/src` → only `schema.d.ts:258`); sprint 01 built the endpoint only.
- All three types are already in the committed client schema (`schema.d.ts:378,431,542`) — no `make generate-api`.

**CSRF — the one existing mechanism, to be reused unchanged.**
- `core/api/client.ts:9-32` is the whole mechanism: a module-memory `csrfToken`, an openapi-fetch middleware that
  sets `X-CSRF-Token` on every non-GET and refreshes the token from any response carrying that header. Nothing
  else in the frontend touches CSRF; there is no hook, no context, no storage (UI-40 forbids storage).
- It is issued on `GET /api/v1/users/me` (`users/routes.py:12`), which `RequireAuth` makes on every page load, and
  on sign-in/register (`auth/routes.py:19-30`); the server compares it to the session row (`auth/dependencies.py:40`).
- Consequence: **a new write needs zero CSRF code.** Calling `api.POST(...)` through `core/api/client.ts` carries
  the header automatically, exactly as `useSignOut` does (proven by `modules/auth/csrf.test.tsx:17-45`).

**Cache invalidation.** `useRunSummaries` uses `queryKey: ["runSummaries"]` (`hooks/useRunSummaries.ts:20`).
`auth`'s mutations use `setQueryData` because they hold the new object; the created `CampaignRunRead` is a different
shape from `CampaignRunSummaryRead` (no title/summary/counts), so this write invalidates instead. Client defaults:
`retry: false`, `staleTime: 30_000` (`core/queryClient.ts`). `invalidateQueries` marks matching queries invalid and
refetches the active ones (@tanstack/react-query 5.102.8 — source: context7, docs v5.90.3); the dashboard is still
mounted when the mutation settles, so the refreshed list is cached before the player returns.

**Placement.** No frontend `modules/content` exists and this sprint does not create one (ASSUMPTION): the catalogue
read is a 15-line hook with one caller, and AGENTS.md promotes shared code only on a *second* caller. The frontend
equivalent of "only `service.py`/`models.py`" is: a module imports another module's declared public surface (its
README "Surface"), never a component or internal file — enforced by `structure.test.ts` 42(c), which allows exactly
one cross-module import (`playthrough` → `auth`'s `useCurrentUser`). Keeping the hook in `playthrough` adds no
cross-module edge and no pinned-test edit. Trade-off: `playthrough` owns a content read until character creation
needs the catalogue too, at which point the hook moves to `modules/content` unchanged — one file, plus one name on
42(c)'s allow-list.

**Dialog.** There is no reusable dialog shell — `InDevelopmentDialog` (`playthrough/components/`) is a standalone
fixed-copy dialog, and MUI's `Dialog`/`DialogTitle` already provide `aria-labelledby`, Escape and backdrop close.
The new dialog is a second standalone component in the same folder. Precedent for ownership of open state:
`PartySection` owns `InDevelopmentDialog`'s. MUI 9.4.0 moved `PaperProps` to `slots`/`slotProps`.

**Design** (binding): `docs/design/dnd-app-dashboard-design/project/Dashboard.dc.html:98-124` — title "Select a
campaign", intro line, a responsive card grid (`repeat(auto-fit, minmax(240px,1fr))`, max-height ~58vh, scrolls),
each card = cover-art slot + title + teaser + "N adventures", and a bordered inset row below the grid showing
`Rolling up "<title>" — taking you to the table.` while creating (`:203-226`). D11 attachment lines 34-35 drop the
tone badge and shorten the intro. The cover-art placeholder already exists as `CampaignCard`'s local `CoverArt`
(`components/CampaignCard.tsx:31-53`) — lift it to a shared spot inside the module; do not invent a second one.

**CampaignCta** (`components/CampaignCta.tsx:53`): the button is `disabled` with no `onClick`. This sprint removes
`disabled`, adds local `useState` open flag + `onClick`, and renders the dialog. Both dashboard call sites
(prominent empty state and footer) are mutually exclusive branches (`DashboardRoute.tsx:91,96-138`), so per-instance
state is safe and `DashboardRoute` needs **no change at all**.

**i18n / tests.** Disjoint subtrees per work item in one namespace file (`playthrough/README.md` Notes): this sprint
owns `dashboard.select.*` in `core/i18n/locales/en/playthrough.json`. No new namespace → `structure.test.ts` UI-43's
pinned `core/` list is untouched, and so are 42(a-c). UI-34 (no hex/rgb/hsl under `src`) is the live trap: the
design's `#9E947F`/`#C9BE9F` must become existing tokens. Tests are Vitest, co-located in the module
(`routes/DashboardRoute.test.tsx` pattern), driven through `renderApp` + `mockRoute`/`getRequests` (`src/test/`);
`make frontend-test`, or `docker compose run --rm --no-deps node-cli pnpm test <path>` for one file.

## Work items

- WI1 *Start a campaign from the dashboard*: the catalogue hook, the create-run mutation, the "Select a campaign"
  dialog (list, creating state, failure state) and the `CampaignCta` button that opens it, plus the `dashboard.select.*`
  copy and one test file covering AC1-AC6.

One item: the catalogue read is one hook shaped like `useRunSummaries`, consumed only by the dialog — splitting it
would cost more hand-off than code.

## Interfaces

Contracts against existing code; no parallel items to synchronise.

```ts
// modules/playthrough/hooks/useCampaignCatalogue.ts
export type CampaignSummary = components["schemas"]["CampaignSummaryRead"];
// { id: string; title: string; summary: string; adventureCount: number }
export function useCampaignCatalogue(): {
  campaigns: CampaignSummary[]; isPending: boolean; isError: boolean; retry: () => void;
};
// GET /api/v1/content/campaigns, queryKey ["campaignCatalogue"], via unwrap(api.GET(...)) — mirrors useRunSummaries.

// modules/playthrough/hooks/useStartCampaignRun.ts
export type CampaignRun = components["schemas"]["CampaignRunRead"];
// { id; campaignId; contentVersion; title: string | null; status; createdAt }
export function useStartCampaignRun(): UseMutationResult<CampaignRun, ApiFailure, string>; // variable = campaignId
// mutationFn: (campaignId) => unwrap(api.POST("/api/v1/playthrough/campaign", { body: { campaignId } }))
// onSuccess: (run) => { queryClient.invalidateQueries({ queryKey: ["runSummaries"] }); navigate(`/runs/${run.id}`); }
//   — not awaited, mirroring useSignIn's onSuccess; CSRF is added by core/api/client.ts's middleware.

// modules/playthrough/components/SelectCampaignDialog.tsx
export interface SelectCampaignDialogProps { open: boolean; onClose: () => void }
```

Behaviour the dialog owns: `mutation.isPending` → the inset "Rolling up …" row (AC2) with the cards disabled;
`mutation.isError` → an `Alert` + "Try again" that re-runs the same campaign id, dialog stays open, nothing created
(AC4) — copy `SignInForm.tsx:118-123`'s mapping (`NETWORK` → `common:errors.network`, else
`common:errors.unexpected`); success unmounts the dialog with the route change (AC2); `onClose` resets the mutation
(AC5). The catalogue read has its own pending/error/retry inside the dialog.

## Open questions

None product-visible. Technical, agent's call, for veto: the catalogue hook stays in `playthrough` until a second
module reads it; `CoverArt` is shared inside the module; the dialog uses `maxWidth="md" fullWidth` instead of the
design's fixed 720/420 px.
