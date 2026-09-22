# character

The character-creation chat, as its own page.

## Owns

- `CreationChatRoute`, the `/runs/:runId/create-character` screen (sprint
  009/06 WI1) — a "Back to the run" button that opens `LeaveDialog` instead
  of navigating directly, the title/subtitle, the transcript, the offered
  choices, the composer and the live sheet panel, side-by-side on a wide
  screen and stacked (panel collapsed into a strip) under `md`.
- `useCreationChat(runId)` — the whole client-side conversation: one
  `useMutation` to start it on mount
  (`POST /api/v1/character/runs/{run_id}/creation`) and one to send a
  message (`POST /api/v1/character/creation/{conversation_id}/messages`),
  feeding a transcript kept in component state (there is no GET behind this
  conversation, so nothing here violates the "server state lives in
  TanStack Query" rule — it simply has no server state to read). A reply's
  `error: true` and a thrown request failure both leave the transcript on
  screen and set `failed`, so "Try again" always re-sends the last player
  text without duplicating it.
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
  (`chat.*`, `choices.*`, `sheet.*`, `leave.*`), registered in
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
