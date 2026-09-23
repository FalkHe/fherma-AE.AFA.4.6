# character

The character-creation chat, as its own page.

## Owns

- `CreationChatRoute`, the `/runs/:runId/create-character` screen (sprint
  009/06 WI1; review/save sprint 009/07 WI1) — a "Back to the run" button
  that opens `LeaveDialog` instead of navigating directly, the
  title/subtitle, the composer and the live sheet panel, side-by-side on a
  wide screen and stacked (panel collapsed into a strip) under `md`. Below
  the title, either the transcript + offered choices, or — once
  `step === "review" && canSave` — `ReviewPanel` in their place (research.md
  Decision 1); the composer stays either way. "Change something" is
  remembered as the transcript length at the moment it's clicked: the review
  stays dismissed until at least two player turns have landed since (the
  "Change something" message itself, and one further message that actually
  names the change) — so the very reply to "Change something" can never
  immediately re-open the review on its own.
- `useCreationChat(runId)` — the whole client-side conversation: one
  `useMutation` to start it on mount
  (`POST /api/v1/character/runs/{run_id}/creation`) and one to send a
  message (`POST /api/v1/character/creation/{conversation_id}/messages`),
  feeding a transcript kept in component state (there is no GET behind this
  conversation, so nothing here violates the "server state lives in
  TanStack Query" rule — it simply has no server state to read); also
  returns `canSave`. A reply's `error: true` and a thrown request failure
  both leave the transcript on screen and set `failed`, so "Try again"
  always re-sends the last player text without duplicating it — an
  `error: true` reply additionally leaves `sheet`/`step`/`canSave`
  untouched, so a failed save cannot drop the player out of the review. A
  `saved: true` reply invalidates `["runOverview", runId]` then navigates to
  `/runs/:runId` — the same invalidate-then-navigate shape
  `useStartCampaignRun` uses, needed because the overview's 30s `staleTime`
  would otherwise show the stale, not-yet-ready party.
- `ReviewPanel` — the finished sheet laid out for a final look (D9/D14 §3):
  name, race, class, level, alignment, hit points, armour class, speed, six
  abilities with their modifiers (`Math.floor((score - 10) / 2)`, computed
  here rather than trusted from the model), skills, equipment, looks and
  backstory, with "Looks right, save" and "Change something" — each sends
  its own label text as the player's message, same rule `OfferedChoices`
  follows. Shows the tavern's in-voice error line inline when the last save
  attempt failed.
- `SheetPanel` — one field list (name, race, class, level, alignment, six
  abilities, hit points, armour class, skills, equipment, "—" for anything
  unset) rendered once, wrapped either in a plain aside or in an `Accordion`
  whose closed summary is the narrow-screen strip; `collapsed` is a prop, not
  an internal media query, so it works the same in a render as it does live.
- `Transcript` — one row per turn, labelled `chat.keeper`/`chat.you`; a
  failed turn adds one retry button below the transcript.
- `Composer` — the free-text row, a real form that submits on Enter.
- `OfferedChoices` — the fixed `step -> buttons` map (the gate's
  "Take {{name}}"/"Make my own" before the player's first turn, three
  buttons at `scores`, one at `equipment`); every button sends exactly its
  own label text.
- `LeaveDialog` — the "Leave character creation?" confirmation (D16).
- `core/i18n/locales/en/character.json` — this module's whole namespace
  (`chat.*`, `choices.*`, `sheet.*`, `leave.*`, `review.*`), registered in
  `core/i18n/index.ts`.

## Surface

- Types re-exported from `useCreationChat.ts`: `CreationReply`, `SheetSoFar`,
  `CreationStep`, `ChatTurn`. No other module imports from `character` yet.
- `playthrough`'s `PlayerCard` takes `createHref` instead of an
  `onCreateCharacter` callback and renders a router `Link`; `PartySection`
  now takes `runId` to build that address. `InviteTile` still opens the
  shared `InDevelopmentDialog` — only "Create character" points here.

## Notes

- "Tavern Keeper" exists only in `character.json`'s `chat.keeper` value
  (D15) — no file, component or identifier in this module spells the name
  out; the wire-level turn tag is the generic `"keeper" | "player"`.
- Leaving mid-conversation keeps nothing: a reload starts over from the
  greeting, and the only in-app exit goes through the confirmation dialog.
  Browser Back is not intercepted (no data router in this app —
  `frontend-stack.md` "Routing").
