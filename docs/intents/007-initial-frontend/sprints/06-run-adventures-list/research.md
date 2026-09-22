---
author: fhit:architect
owner: agent
created: 2026-09-22
---
# Research: Sprint 06 — run adventures list

Frontend only. The overview read already carries every adventure fact the brief needs; nothing on the backend moves.

## Facts

- `adventures[]` is `CampaignRunAdventureRead` = `id, title, introExcerpt, status` and nothing else
  (`frontend/src/api/schema.d.ts:306-313`; source `backend/app/modules/playthrough/schemas.py:61-71`).
  `status` types as a plain `string`; the only values the service emits are `"done"` (an `adventure_runs` row with
  `completed`), `"active"` (a row with `active`) and `"unplayed"` (no row) —
  `backend/app/modules/playthrough/service.py:424-431`.
- Order is the campaign's own: the content loader builds `LoadedCampaign.adventures` as a dict inserted in
  `campaign.adventures` order (`backend/app/modules/content/service.py:143-163`), and `get_run_overview` iterates
  that dict (`service.py:424`). Rendering the array as it arrives satisfies AC1 — no client sort.
- The teaser exists: `introExcerpt` is the adventure's `intro` clipped to 200 chars on a word boundary
  (`backend/app/modules/playthrough/service.py:358-370`). No extra read needed.
- **There is no "next up" flag and no "waiting" reason in the payload.** Both are derivable from fields already on
  screen, so no backend work: the current adventure is the first whose `status !== "done"`; the party is blocked when
  any `members[].ready` is `false` — the same array `PartySection` already counts
  (`frontend/src/modules/playthrough/components/PartySection.tsx:26`). The delivered design does exactly this and
  states the reason as one fixed sentence, not an API string: "Every player needs a character before the first
  adventure can start", shown next to the section heading while blocked
  (`docs/design/dnd-app-dashboard-design/project/CampaignRun.dc.html:74-77`, state derived at `:152-160`).
- Badge-word convention (AC5's "no invented status"): sprint 05 maps the raw wire status to dashboard wording in a
  local `statusKey()` switch with a safe default, keys under `playthrough:run.status.*`
  (`frontend/src/modules/playthrough/routes/RunRoute.tsx:31-44`; rationale in
  `frontend/src/modules/playthrough/README.md`). This sprint mirrors that shape one-to-one.
- i18n: one namespace file, subtree per work item — `run.*` and `party.*` are taken
  (`frontend/src/core/i18n/locales/en/playthrough.json`). This sprint owns `adventures.*`. The file itself is already
  pinned in `frontend/src/structure.test.ts:167`; adding keys inside it changes nothing there. No other pin in that
  suite touches `modules/playthrough` (it pins `core/`, `home`↔`auth` imports and the colour-literal ban, which
  applies here: no hex/rgb value — use `var(--…)` tokens, as `PlayerCard.tsx:36-78` does).
- `RunRoute.tsx:88-101` renders header then `<PartySection members={…} />`; the adventures section slots in directly
  after, off the same `overview` object. `unavailable: true` already collapses into `notFound` before that branch
  (`hooks/useRunOverview.ts:40-42`), so the empty-`adventures` case never reaches the section.
- Tests: one file per screen, `frontend/src/modules/playthrough/routes/RunRoute.test.tsx`, rendering through
  `renderApp` + `mockRoute` (`frontend/src/test/`); its `OVERVIEW` fixture currently has `adventures: []`. Runner:
  `make frontend-test`, single file `docker compose run --rm --no-deps node-cli pnpm test <path>`.
- `@mui/material` 9.4.0 (`frontend/pnpm-lock.yaml:395`): a `disabled` button fires no hover or focus events; the
  documented pattern is a `<span>` wrapper inside `Tooltip` — MUI 9 docs, components/tooltips "Disabled elements"
  (source: context7 `/mui/material-ui/v9.2.0`, nearest published minor). A disabled button is also not focusable, so
  the brief's "hover **and focus**" cannot both hold; the always-visible section hint carries the reason for keyboard
  and screen-reader users instead.

## Work items

- WI1 (frontend): the adventures section on the run screen — one row per adventure with roman numeral, title,
  `introExcerpt` teaser and a Next up / Waiting on party / Locked / Done badge, the blocked-reason hint beside the
  heading, a "Start adventure" button on the current row that is disabled and wired to nothing, its `adventures.*`
  keys, the two lines wiring it into `RunRoute`, and the tests below.

One work item: the section, its row and the three-line route wiring are one component tree with no seam worth two
agents.

## Interfaces

- `modules/playthrough/components/AdventuresSection.tsx` (WI1 owns), consumed by `RunRoute.tsx`:
  ```ts
  import type { RunOverview, RunMember } from "../hooks/useRunOverview";
  type RunAdventure = RunOverview["adventures"][number]; // id, title, introExcerpt, status
  export function AdventuresSection(props: { adventures: RunAdventure[]; members: RunMember[] }): ReactElement;
  ```
  Rendered in `RunRoute.tsx` right after `<PartySection …>`, inside the same `overview` branch:
  `<AdventuresSection adventures={overview.adventures} members={overview.members} />`.
- Derivation, fixed here so AC5 is checkable (both values come from the payload; only the wording is ours):
  ```ts
  const partyReady = members.length > 0 && members.every((m) => m.ready);
  const currentIndex = adventures.findIndex((a) => a.status !== "done");   // -1 → every adventure done
  // badge key per row i:
  //   a.status === "done"      -> "adventures.status.done"
  //   i === currentIndex       -> partyReady ? "adventures.status.nextUp" : "adventures.status.waitingOnParty"
  //   otherwise                -> "adventures.status.locked"
  // "Start adventure" renders on row `currentIndex` only, always disabled, no onClick.
  ```
- Translation keys (WI1 owns `playthrough:adventures.*` exclusively; `run.*`/`party.*` untouched):
  `adventures.heading`, `adventures.waitingHint`, `adventures.start`,
  `adventures.status.{nextUp,waitingOnParty,locked,done}`. Copy follows the design:
  heading "Adventures", hint "Every player needs a character before the first adventure can start."
- Numerals are derived from the row index (I, II, III …), not copy — no translation key, no library; decimal
  fallback past the numeral table.
- Tests extend `RunRoute.test.tsx` with an `adventures` fixture: (a) rows render in payload order with numeral, title,
  teaser and badge; (b) with one member not ready, row 1 reads "Waiting on party", the hint is present and the button
  is disabled; (c) with every member ready it reads "Next up"; (d) a `done` row reads "Done" and later rows "Locked".

## Open questions

- *Technical.* An adventure with `status: "active"` reads as the current row ("Next up" / "Waiting on party"), because
  D9 names no word for an adventure already under way. Unreachable in this intent — nothing in the UI can start one —
  so it needs no decision now; it becomes product-visible the moment adventure entry ships and should be decided then.
- *Technical.* The disabled button's explanation is hover-only (a disabled button takes no focus, MUI 9 above), which
  narrows the brief's "hover and focus" assumption. The reason is not hidden by this: the section hint states it in
  plain sight whenever the party is blocked. No alternative worth the complexity.
