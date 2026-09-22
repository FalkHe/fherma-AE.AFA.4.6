---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 09

Frontend only, one work item. `POST /api/v1/playthrough/campaign` already exists, already allows repeat starts, and
its types are already in the committed client schema — no backend work. This is the intent's first write; the CSRF
mechanism it must reuse already exists and must not be reinvented.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | frontend | The dashboard's "Create new campaign" button opens a "Select a campaign" dialog listing every catalogue campaign with placeholder art, title, teaser and adventure count; choosing one creates the run, shows the rolling-up state and lands on that run's screen; starting the same campaign twice is allowed and leaves two runs; a failed creation keeps the dialog open with a retry and creates nothing; dismissing creates nothing | the dialog lists the catalogue; choosing creates exactly one run and navigates to it; a second start of the same campaign neither warns nor blocks and the dashboard then shows both; a failed create keeps the dialog open, offers retry and issues no second write; dismissing issues no write | – |

## Interfaces
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

// modules/playthrough/components/SelectCampaignDialog.tsx
export interface SelectCampaignDialogProps { open: boolean; onClose: () => void }
```

- **CSRF — reuse, never reinvent.** `frontend/src/core/api/client.ts` is the entire mechanism: a module-memory token
  plus an openapi-fetch middleware that stamps `X-CSRF-Token` on every non-GET and refreshes it from any response
  carrying that header. `GET /api/v1/users/me` issues it on every page load via `RequireAuth`. Calling `api.POST(...)`
  through that client is the whole requirement — `useSignOut` does nothing else.
- **Invalidation:** `queryClient.invalidateQueries({ queryKey: ["runSummaries"] })` in `onSuccess`, not awaited, then
  navigate. Not `setQueryData`: `CampaignRunRead` is a different shape from `CampaignRunSummaryRead`.
- **Create endpoint:** `POST /api/v1/playthrough/campaign`, body `{"campaignId"}`, 201 → the run. Errors 401, 403
  `CSRF_TOKEN_INVALID`, 404 `NOT_FOUND`. `ALREADY_STARTED` cannot fire for a repeat start — the uniqueness is
  per-run, deliberately.
- **`CampaignCta.tsx`:** drop `disabled`, add a local open flag and `onClick`, render the dialog. `DashboardRoute`
  needs no change — its two call sites are mutually exclusive branches, so per-instance state is safe.
- i18n: `dashboard.select.*` inside the existing `playthrough.json`. A new namespace would force editing
  `structure.test.ts`'s pinned `core/` list for nothing.

## Acceptance tests (qa)
No separate qa agent, as in sprints 05–08.
- AC1–AC6 → one new Vitest file in the module, asserting through `renderApp` + `mockRoute`/`getRequests` so the
  "creates nothing" criteria are checked against actual requests issued, not against rendering alone.

## Order
WI1 alone.
