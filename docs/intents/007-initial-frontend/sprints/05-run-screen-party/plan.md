---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 05

Frontend only — the run-overview read shipped in sprint 02 and carries every field the brief needs.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | frontend | The `/runs/<id>` address opens a page showing the campaign title, description and a run status badge, with a back link to the campaigns page, a loading state, a retryable error state and a plain not-found message; the signed-in shell is wide enough for the design | route renders title/description/badge from one read; error offers retry; unknown run says not found; back link goes to campaigns | – |
| 2 | frontend | A party section reading "n of m characters ready" with one card per player (initial, name, role badge, character state or "No character yet", "Create character" button) and an "Invite a player · Up to six at the table" tile; both buttons open the in-development dialog | – (covered by WI1's route test where cheap) | I1, I2 |
| 3 | frontend | One reusable "in development" dialog component whose copy lives in translation keys | – | – |

## Interfaces
- I1: `modules/playthrough/hooks/useRunOverview.ts` (WI1 owns)
  ```ts
  export type RunOverview = components["schemas"]["CampaignRunOverviewRead"];
  export type RunMember = components["schemas"]["CampaignRunMemberRead"];
  export function useRunOverview(runId: string): {
    overview: RunOverview | null;  // null while pending, on error, on 404
    isPending: boolean;
    isError: boolean;   // false when notFound is true
    notFound: boolean;  // failure.status === 404
    retry: () => void;
  };
  // queryKey ["runOverview", runId]
  // api.GET("/api/v1/playthrough/runs/{run_id}/overview", { params: { path: { run_id: runId } } })
  ```
- I2: `modules/playthrough/components/PartySection.tsx` (WI2 owns), consumed by WI1's route
  ```ts
  export function PartySection(props: { members: RunMember[] }): ReactElement;
  ```
- I3: `modules/playthrough/components/InDevelopmentDialog.tsx` (WI3 owns), consumed by WI2
  ```ts
  export function InDevelopmentDialog(props: { open: boolean; onClose: () => void }): ReactElement;
  // no copy props: reads common:inDevelopment.title / .body / .close
  ```
- Translation ownership, so no two work items touch one key: WI1 owns `playthrough:run.*`, WI2 owns `playthrough:party.*`, WI3 writes `common.json` only.
- API: `GET /api/v1/playthrough/runs/{run_id}/overview` → `id, campaignId, contentVersion, title, status, createdAt, campaignTitle, campaignSummary, unavailable, members[], adventures[]`; member = `userId, username, role, ready, characterName`. 404 (`NOT_FOUND`) for both unknown and foreign runs.

## Acceptance tests (qa)
Deliberately thin — the sprint lead asked for minimal test effort; the screen is verified in the browser against the preview URL.
- AC1, AC5 → one `RunRoute.test.tsx` covering render, error-retry and not-found.
- AC2, AC3, AC4 → verified in the browser on https://tc-ae-s04-st3ll4.hermann.pm/.

## Order
Parallel: WI1, WI3. Then: WI2.
