---
author: architect
owner: agent
created: 2026-09-23
---
# Research: Sprint 009-07 — review, save and the finished character

## Facts

- `SheetSoFar` (`backend/app/modules/character/schemas.py:226-245`) already carries every AC1 field
  including `speed`, `appearance`, `backstory` — **no wire change needed for the review**. It carries
  no ability modifiers; `Abilities` is six raw scores.
- `step` only reaches `review` once all six checks pass (`service.py:322-336`), so
  `step === "review" && canSave` is a sound gate — `canSave` alone is true much earlier.
- `show_sheet(ready_made=True)` (`agent/tools.py:355-365`) returns rendered text and **writes nothing
  to the draft**, so `creation_progress` still reports `raceClass`/`canSave: false`: today the
  ready-made path never reaches a review. The prompt already saves on a plain yes
  (`prompts/v1/system/creator.md:17-23`).
- `SeedCharacter` (`content/schemas.py:128-137`) has no alignment, speed or skills; the shipped seed's
  race/class are SRD names (`content/campaigns/greenhollow/v1/campaign.json:8-9`).
- `CampaignRunMemberRead` (`playthrough/schemas.py:49-59`) exposes only `ready` + `character_name`; the
  overview query selects `GameObject.name` alone (`playthrough/service.py:395-415`). Race, class, level
  and appearance live in the object's `state` blob (`CharacterState`, `schemas.py:161-194`);
  `current_hp`/`max_hp`/`armour_class` are columns. `CharacterRead` (`:150-158`) has one caller,
  `playthrough/routes.py:127`.
- Party line and "Next up" already derive from `ready` (`PartySection.tsx:27,36`,
  `AdventuresSection.tsx:4-7`) — both flip for free once a character exists.
- `PlayerCard.tsx:92` renders "Create character" unconditionally — AC4 needs it hidden when ready.
- Query `staleTime` is 30 s (`core/queryClient.ts:11`), so plain navigation would show the stale run
  screen; `useStartCampaignRun.ts:43` is the invalidate-then-navigate precedent.
- Tests: `mockRoute` answers one route twice from an array (`test/network.ts:44-53`), `getRequests`
  counts calls, `renderApp`/`getPathname` (`test/render.tsx:91-112`); `structure.test.ts` pins files
  under `core/` only, so new module components are free.

## Decisions (technical)

1. **Review is a state of the creation page, not a route**: `ReviewPanel` replaces `Transcript` +
   `OfferedChoices` when `step === "review" && canSave` and the player has not just asked to change
   something; the composer stays. No route, no second data source. Blast radius: one `if` in
   `CreationChatRoute`.
2. **"Change something" dismissal**: the route keeps one number — the player-turn count at dismissal —
   and shows the review again once the player has sent one further message (← brief's assumption).
3. **Modifiers are computed in the browser** as `Math.floor((score - 10) / 2)`: display arithmetic
   over numbers the backend already fixed, not a rule the model invents (← project rule).
4. **Ready-made review**: `show_sheet(ready_made=True)` additionally writes `{"ready_made": True}` to
   the draft, and `creation_progress` renders the seed when that flag is set *and* no race is in the
   draft — so a player who then builds their own falls back to the normal path with no extra
   bookkeeping. Alignment, speed and skills stay empty for the seed hero (it has none); the review
   shows "—" there.
5. **Character card data** rides the overview, not a second call: `CharacterRead` gains the four sheet
   facts the card shows and the member entry carries it whole, replacing `characterName` — one shape
   instead of seven flat fields, `null` for a member without a character exactly as before.
6. **Save → return** lives in `useCreationChat`: on `saved: true`, invalidate `["runOverview", runId]`,
   then navigate — without it the 30 s `staleTime` shows the old party. A failed save leaves
   `step`/`canSave` untouched, so the review stays and renders the last Keeper line; pressing "Looks
   right, save" again retries.

## Work items

- WI0 (backend-python): fact 5's schema/query change plus decision 4's tool and `creation_progress`
  change, backend tests for both, then `make generate-api` and commit `openapi.json` + `schema.d.ts`.
- WI1 (frontend, after WI0): `ReviewPanel`, the hook's `canSave`/save handling, `CharacterCard`,
  `PlayerCard`, both locale files, READMEs, six tests.

## Interfaces

- `CharacterRead` gains `race: str`, `character_class: str`, `level: int`, `appearance: str` → wire
  `race`, `characterClass`, `level`, `appearance`, read via `CharacterState.model_validate(obj.state)`.
  One helper in `playthrough/service.py` builds it; `routes.py:127` uses it too.
- `CampaignRunMemberRead.character_name` → `character: CharacterRead | None`; `ready = character is not
  None`; the member query selects the `GameObject` entity. Callers: `character/service.py:482`,
  `PlayerCard.tsx:89`, the backend tests above, three frontend fixtures.
- `show_sheet(ready_made=True)` returns `Command(update={"draft": {"ready_made": True}, "messages":
  [ToolMessage(content=<the rendered seed text>, …)]})` — the content must stay the rendered string, or
  `service.turn`'s collector (`service.py:266-273`) stops printing it.
- `creation_progress(draft, *, seed=None, seed_items=None)`; `_reply_for` passes `conversation.seed`
  and `conversation.ready_made_items` (it already carries the seed's name). Ready-made branch answers
  `step="review"`, `step_number=7`, `can_save=True`, sheet from `seed` (`backstory` ← `seed.background`,
  `equipment` ← `seed_items`).
- `useCreationChat` additionally returns `canSave: boolean`; in both mutations' `onSuccess`, a reply
  with `saved: true` runs `queryClient.invalidateQueries({ queryKey: ["runOverview", runId] })` then
  `navigate("/runs/" + runId)`.
- `ReviewPanel({ sheet, failed, errorText, onSave, onChange })` in `modules/character/components/`.
  Buttons send exactly their own label text: `t("review.save")` = `"Looks right, save"`,
  `t("review.change")` = `"Change something"` (same rule `OfferedChoices` already follows).
- `CharacterCard({ character })` in `modules/playthrough/components/` — name, `Halfling Rogue · Level
  1`, HP, AC, appearance clamped to three lines, "Ready" badge; `PlayerCard` renders it when
  `member.character` is set and drops the "Create character" button then.
- New keys — `character.json`: `review.{title,subtitle,save,change}`,
  `sheet.fields.{speed,looks,story}` (the rest reuse `sheet.fields.*`); `playthrough.json`:
  `party.card.{ready,raceClass,hp,ac}`. Copy from D14 §3: "One last look" / "This is who walks into
  the tavern. Saving makes it final for this run."
- Tests, one per criterion: AC1 a mocked `review` reply renders every field; AC2 "Change something"
  posts its text and brings the transcript back, "Looks right, save" posts its text; AC3 a
  `saved: true` reply lands on `/runs/r1` and a second overview GET is recorded; AC4 a `PlayerCard`
  with a character shows name, race/class, level, HP, AC, looks, no "Create character", and the party
  line counts it; AC5 an `error: true` save reply keeps the review with the in-voice line; AC6 the
  review's copy equals the locale values.

## Open questions

None product-visible.
