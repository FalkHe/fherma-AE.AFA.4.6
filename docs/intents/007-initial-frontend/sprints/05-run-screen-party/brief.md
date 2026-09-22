---
author: fhit:architect
owner: human
created: 2026-09-22
stage: draft
---
# Sprint 05: run screen with party

## Task
Add the campaign-run screen at its own address, fed by the run overview: back link to the campaigns page, status badge,
campaign title and description, and a party section stating how many characters are ready with one card per player
carrying initial, name, role and character state, plus a "Create character" button. Add the "Invite a player" tile and
the single "in development" dialog that both it and "Create character" open.

## Outcome
Opening a run's address shows its campaign title, the owner's card reading "No character yet", and clicking either
"Create character" or "Invite a player" opens a dialog saying the feature is in development.

## Acceptance criteria
- AC1: The run address renders the campaign title, description and run status badge from one overview read, with a
  loading state and a retryable error state (← D11).
- AC2: The party section reads "n of m characters ready" and renders a card per player with initial, name, role badge
  and character state — "No character yet" or the character's name (← D11).
- AC3: "Create character" looks active and opens the in-development dialog; the "Invite a player · Up to six at the
  table" tile opens the same dialog (← D4, D13).
- AC4: That dialog is one component with its copy in translation keys, along the lines of "Be brave, this feature is
  in development", usable by any later feature (← D13).
- AC5: A back link returns to the campaigns page, and a run that does not exist or is not the player's shows a plain
  not-found message.

## Decisions
← D4, D11, D13

## Assumptions
- The address is `/runs/<id>`; a new frontend playthrough module mirrors the backend one.
- Not-found and not-a-member read identically to the player.
- The whole screen is one query; the player card has no e-mail line because users have none.

## Out of scope
No adventures section (06) · no real character creation or invite · no play/session view · no rename or archive.
