# playthrough

The run screens: opening one run's campaign, its party and (sprint 06) its
adventures.

## Owns

- `RunRoute`, the `/runs/:runId` screen — back link, status badge, campaign
  title and description, loading / retryable-error / not-found states
  (sprint 007/05 WI1).
- `useRunOverview(runId)`, the one read behind that screen —
  `GET /api/v1/playthrough/runs/{run_id}/overview`. A 404 (unknown run or a
  run that isn't the caller's — the server can't tell them apart) and a 200
  with `unavailable: true` (the run's pinned campaign content is gone) both
  fold into the same `notFound` flag; the caller never has to tell them
  apart either.
- `PartySection` — the "n of m characters ready" readout plus one
  `PlayerCard` per member and an `InviteTile` for open seats; both the card's
  "Create character" button and the tile open `InDevelopmentDialog` (WI3,
  keys in `common`), whose open state `PartySection` alone owns (WI2).

## Surface

- `RunOverview`/`RunMember` (re-exported off the generated `components["schemas"]`
  types) and `useRunOverview` are this module's one interface outward; no
  other module imports from `playthrough` yet.

## Notes

- Translation keys are disjoint per work item in one
  `core/i18n/locales/en/playthrough.json`: WI1 owns `run.*`, WI2 owns
  `party.*`.
- The status badge reuses the dashboard's own wording (`run.status.new` /
  `.inProgress` / `.archived`), not the raw `setup|ready|active|archived|finished`
  status, so the run screen and the dashboard (sprint 07) read as one voice.
- The back link goes to `/` — today's landing route, becoming the dashboard
  of runs in sprint 07 ("the campaigns page" the brief refers to).
