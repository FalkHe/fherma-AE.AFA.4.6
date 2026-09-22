---
author: architect
owner: agent
created: 2026-09-23
---
# Research: Sprint 009-06 — the creation page

## Facts

- Routes are declarative `<Routes>` inside one guarded pathless layout route (`App.tsx:20-33`);
  `frontend-stack.md` "Routing" pins **no data routers, no loaders**.
- react-router **8.3.1** (`frontend/pnpm-lock.yaml:1455`, local source). `useBlocker` opens with
  `useDataRouterContext("useBlocker")` (`node_modules/react-router/dist/development/lib/hooks.js:1250-1252`),
  which `invariant`s outside a data router — **unusable** under `BrowserRouter`/`MemoryRouter`.
  `useBeforeUnload` (`…/lib/dom/lib.js:1167`) is a plain listener and works anywhere.
- `PartySection.tsx:24,48-53` owns one dialog flag shared by `PlayerCard`'s "Create character"
  (`PlayerCard.tsx:90`) and `InviteTile`. No test anywhere asserts that dialog (grep over
  `*.test.tsx`), so AC1 breaks nothing.
- `CreationReply` (`frontend/src/api/schema.d.ts:571-589`) carries `reply, sheet, step, stepNumber,
  canSave, saved, error` — **no offered-choices list and no ready-made hero name**; the name exists
  only inside the greeting prose (`backend/app/modules/character/service.py:205-214`). `SheetSoFar`
  (`:680-712`) is all-nullable plus `skills`/`equipment` arrays.
- One client, one failure shape: `unwrap()` throws `ApiFailure {code, status}`, `code: "NETWORK"`
  when fetch itself rejects (`core/api/errors.ts:56-72`).
- i18n: one namespace per module, registered in `core/i18n/index.ts:6-12`. `structure.test.ts:159-206`
  pins the **exact** file list under `core/` — a new locale file needs one line added there.
  `structure.test.ts:70,148` bans `localStorage`/`sessionStorage`/`document.cookie` anywhere in `src`.
- `common:actions.retry` is already "Try again" (`locales/en/common.json`).
- Tests: `renderApp(["/path"])` + `getPathname()` (`test/render.tsx:91-112`), `mockRoute`
  (`test/network.ts:50`); an unstubbed request throws (`network.ts:127`). `matchMedia` is stubbed
  `matches: false` (`test/setup.ts:151`), so `useMediaQuery` always reads the wide layout in tests.

## Decisions (technical)

1. **Route** `/runs/:runId/create-character`, one more child of the guarded layout route. Nothing is
   stored in the browser, so a reload simply starts a fresh conversation on mount (← D12; the run
   screen is unchanged either way). Blast radius: one line in `App.tsx`.
2. **Offered choices** (AC2) come from a fixed `step → choices` map, not from the reply: `scores` →
   three buttons, `equipment` → "Just the default" (← D14 §1.6, §1.11). Each button sends exactly its
   own label text, so a button and typing are literally the same input. The gate offer
   ("take <hero>") gets **no** button: its text needs the hero's name, which no route returns —
   parsing it out of the greeting would couple the page to backend prose. Trade-off and the small API
   addition that would fix it are the one open question below.
3. **Leave dialog** (AC4, D16) without `useBlocker`: the page renders exactly one in-app exit, a
   "Back to the run" link that opens the dialog instead of navigating; "Leave" then navigates to
   `/runs/:runId`. `useBeforeUnload` covers reload and tab close. Browser **Back is not intercepted**
   — blocking it needs a data router (fact 2) or a history hack; failure mode is that Back leaves
   without asking, and nothing is lost that leaving would not discard anyway (D14 §1.16).
4. **Errors** (AC5): a reply with `error: true` already carries the in-voice line — render it as a
   Keeper turn. A thrown `ApiFailure` (any status) renders the page's own `character:chat.error` key
   with the same wording. Either way the transcript stays, and "Try again"
   (`common:actions.retry`) re-sends the last player text without duplicating the player turn.
5. **State**: one hook, `useCreationChat(runId)`, holding two `useMutation`s (start on mount, send)
   and the transcript in component state. Deviation from "no server data in `useState`" is deliberate:
   there is no GET behind this conversation, it exists only as the sequence of replies, so it is
   client-owned. `canSave`/`saved` are read but unused — sprint 07.
6. **Sheet panel** renders the field list **once** inside one of two frames chosen by
   `useMediaQuery(down("md"))`: a side panel, or an `Accordion` whose summary is the strip
   `Halfling Rogue · Level 1 · step 2 of 7`. One list, no duplicated DOM, no ambiguous queries.
7. **New module** `frontend/src/modules/character/` with its own `character` namespace
   (`core/i18n/locales/en/character.json`), registered in `core/i18n/index.ts` and added to the pinned
   list in `structure.test.ts`. No import from `playthrough`: the back link is a plain key, not the
   campaign title, which drops the wireframe's second exit link and its campaign name (ASSUMPTION).

## Work items

- WI1 (frontend, single agent): the whole page, its module README, the locale file, route
  registration, the run-screen button change and the six tests. The run-screen edit is six lines and
  shares the route path with the page, so splitting it into a second work item would cost more
  coordination than it saves.

## Interfaces

- Route `/runs/:runId/create-character` → `CreationChatRoute` (`modules/character/routes/`).
- `modules/character/hooks/useCreationChat.ts`:
  `useCreationChat(runId: string) => { turns: { speaker: "keeper" | "player"; text: string }[];
  sheet: SheetSoFar | null; step: CreationStep | null; stepNumber: number; isSending: boolean;
  failed: boolean; send(text: string): void; retry(): void }`, over
  `POST /api/v1/character/runs/{run_id}/creation` and
  `POST /api/v1/character/creation/{conversation_id}/messages` (sprint 05 contract, unchanged).
  Types re-exported from `components["schemas"]`: `CreationReply`, `SheetSoFar`,
  `CreationStep = CreationReply["step"]`.
- Components: `SheetPanel({ sheet, stepNumber, collapsed })`, `LeaveDialog({ open, onStay, onLeave })`,
  `Transcript({ turns, failed, onRetry })`, `Composer({ onSend, disabled })`,
  `OfferedChoices({ step, onPick })`.
- `PartySection` gains `runId: string`; `PlayerCard`'s `onCreateCharacter` becomes
  `createHref: string` and the button renders as a router `Link`. `InviteTile` keeps
  `InDevelopmentDialog`.
- Keys in `character.json`: `chat.{title,subtitle,back,keeper,you,placeholder,send,error}`,
  `choices.{suggestScores,rollScores,spendScores,defaultEquipment}`,
  `sheet.{heading,step,strip,empty}` + `sheet.fields.*` (name, race, class, level, alignment,
  abilities.str…cha, hitPoints, armourClass, skills, equipment),
  `leave.{title,body,stay,leave}`. Retry reuses `common:actions.retry`.
- Tests, one per criterion, testing-library + `mockRoute`: AC1 `renderApp(["/runs/r1"])`, click
  "Create character", `getPathname()` is `/runs/r1/create-character`; AC2 the greeting and a player
  turn render, a choice button posts its own label as `text`; AC3 `SheetPanel` shows set fields, "—"
  for empty and "Step 2 of 7", collapsed and not; AC4 the back link opens the dialog and "Leave"
  lands on `/runs/r1`; AC5 an `error: true` reply shows the line and "Try again" re-posts the same
  text; AC6 the page's copy matches the `character.json` values (no raw key on screen).

## Open questions

- Product-visible: at the start the Keeper offers the ready-made hero by name, and this sprint gives
  that offer no button — the player types the phrase the greeting spells out, while the later
  ability-score and equipment offers do get buttons. Making it a button needs the reply to carry the
  hero's name, a small addition to the just-shipped API; worth doing in sprint 07, or leave as is?
