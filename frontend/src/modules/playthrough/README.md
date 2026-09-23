# playthrough

The signed-in landing dashboard and the run screens: choosing a campaign run,
then its party and its adventures.

## Owns

- `DashboardRoute`, the `/` screen — the greeting, a tag row (`In progress` /
  `New` / `Archived`) that filters the run list to one group at a time (the
  chosen tag lives in component state only, never persisted), each card
  (cover-art placeholder, title, status badge, teaser, the "Adventure n of m
  · k players · Created <relative date>" line, a Begin/Resume action) newest
  first within its group, the empty-state invitation card, and the "Start a
  new campaign" card, which opens `SelectCampaignDialog`. The dashboard opens
  on In progress, falls back to New when nothing is in progress, and shows
  only the invitation with no tags at all when there are no runs; a tag with
  no runs in it shows a short "nothing here" line instead of an empty list.
  An archived card renders muted with no action block at all — it cannot be
  opened — under a note above the list saying archived runs are kept as they
  are and are view-only. Replaces the retired `modules/home`'s `HomeRoute`.
- `useRunSummaries()`, the dashboard's one read —
  `GET /api/v1/playthrough/runs`. Server order is rendered as received and
  never re-sorted in the browser; the tag filter is applied client-side only,
  there is no server-side filter parameter.
- `CampaignCta` owns its own "Select a campaign" dialog-open flag (one
  instance per branch of `DashboardRoute`'s two mutually exclusive call
  sites, so nothing needs lifting or sharing — same house pattern as
  `PartySection`'s `InDevelopmentDialog`). `SelectCampaignDialog` lists every
  campaign in the catalogue (`useCampaignCatalogue()` —
  `GET /api/v1/content/campaigns`) as a clickable card (placeholder art
  reusing `CoverArt`, title, teaser, adventure count; no tone badge — the
  wire shape carries none). Picking one runs `useStartCampaignRun()`
  (`POST /api/v1/playthrough/campaign`), which disables every card and shows
  an inset "Rolling up …" row while in flight, then navigates to the new
  run's screen and invalidates `["runSummaries"]` in the background so the
  dashboard is current by the time the player returns. A failed start shows
  a retryable error inline without closing the dialog; dismissing the dialog
  (`Escape`, a backdrop click, or the header's `×` close button) issues no
  request at all and resets the mutation. Starting the same campaign twice is
  unrestricted by design — the uniqueness constraint behind the endpoint is
  per-run, not per-campaign-per-player — so it simply creates a second run.
- `runStatus.ts` — `runStatusKey`/`runActionKey`, the run-status vocabulary
  shared by `RunRoute` and the dashboard (`run.status.new/.inProgress/.archived`,
  `dashboard.card.begin/.resume`). `runStatusKey`'s three values are also the
  dashboard's tag set, so a card's badge and the tag it files under can never
  disagree. `runActionKey` returns `null` for an archived or finished run —
  the dashboard renders no action block for it.
- `relativeDate.ts` — `formatRelativeDate`, an `Intl.RelativeTimeFormat`
  wrapper for the card's "Created …" line (no date library).
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
  `PlayerCard` per member and an `InviteTile` for open seats; the tile opens
  `InDevelopmentDialog` (WI3, keys in `common`), whose open state
  `PartySection` alone owns (WI2). The card's "Create character" button is a
  link to `character`'s own creation-chat page (`/runs/:runId/create-character`,
  sprint 009/06 WI1) — `PartySection` takes `runId` to build that address and
  passes it to `PlayerCard` as `createHref`. The readout counts `member.ready`,
  unaffected by whether a character is rendered as a card or a plain row.
- `PlayerCard` renders `CharacterCard` in place of the ready/not-ready row
  and the "Create character" link once `member.character` is set (sprint
  009/07, WI1, AC4) — a saved character has no edit affordance (D14 §1.15),
  so the link has nothing left to do.
- `CharacterCard` — the finished character on the run screen (D14 §3): name,
  `{race} {class} · Level {n}`, hit points, armour class, a "Ready" badge,
  and the looks clamped to three lines. Takes the widened `CharacterRead`
  WI0 ships this sprint (`race`, `characterClass`, `level`, `appearance`
  alongside the existing `name`/`maxHp`/`armourClass`).
- `AdventuresSection` — one numbered row per adventure in campaign order;
  the first unplayed one reads "Next up"/"Waiting on party" from whether
  every seated member is ready, later rows read "Locked", finished ones
  "Done", and a disabled "Start adventure" sits on the current row only
  (sprint 007/06 WI1). An adventure already under way (`status: "active"`)
  reads "In progress" instead, with a "Continue" link to that run's play
  screen (`/runs/:runId/play`) rather than the disabled button (sprint
  010/06 WI5).

## Surface

- `RunOverview`/`RunMember`/`RunSummary`/`CampaignSummary`/`CampaignRun`
  (re-exported off the generated `components["schemas"]` types) and
  `useRunOverview`/`useRunSummaries`/`useCampaignCatalogue`/
  `useStartCampaignRun` are this module's interface outward; no other module
  imports from `playthrough` yet. `DashboardRoute` imports `useCurrentUser`
  from `auth` — the one permitted cross-module edge (structure.test.ts
  criterion 42(c)).
- `CoverArt` — the shared cover-art placeholder box, used by both
  `CampaignCard` (the dashboard's run cards) and `SelectCampaignDialog` (the
  catalogue cards), so the gradient-and-label markup exists in one place.

## Notes

- Translation keys are disjoint per work item in one
  `core/i18n/locales/en/playthrough.json`: sprint 05 WI1 owns `run.*`, WI2
  owns `party.*`; sprint 06 WI1 owns `adventures.*`; sprint 07 WI1 owns
  `dashboard.*` and sprint 08 WI1 owns `dashboard.tags.*` within it; sprint
  09 WI1 owns `dashboard.select.*` within it; intent 009 sprint 07 WI1 adds
  `party.card.{ready,raceClass,hp,ac}` within `party.*`.
- The status badge reuses the dashboard's own wording (`run.status.new` /
  `.inProgress` / `.archived`), not the raw `setup|ready|active|archived|finished`
  status, so the run screen and the dashboard read as one voice — both pull
  it from the shared `runStatus.ts`.
- Two different things mute a dashboard card, checked in this order —
  availability first, status second: an *unavailable* run (its pinned
  campaign content is gone) renders with no open action and a "why" trigger
  that reveals a plain inline explanation on click, rather than reusing
  `InDevelopmentDialog`, whose copy doesn't fit this reason (decision, sprint
  brief), regardless of its status; only once a run is available does an
  *archived* status mute the card with no action block and no trigger at
  all — nothing can explain or undo it, so there is nothing to click.
- The back link on `RunRoute` goes to `/`, the dashboard.
