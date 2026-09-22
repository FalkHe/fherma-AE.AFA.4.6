---
author: sprint
owner: agent
created: 2026-09-21
updated: 2026-09-21
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/39
---
# Review: Sprint 02 — recall by meaning, and a recap on return

## What changed

The narration stored in the last sprint can now be found. Asking a run a question returns the lines of narration
closest to it in meaning — anywhere in the run, including adventures it has long since left — closest first and
with no cut-off, so whatever the run remembers best comes back. A run can also be asked for its recap: its newest
narration, oldest first, which is what a resumed game needs when there is nothing yet to match on. Both are
usable from the command line; neither is wired into the Dungeon Master yet.

## How to check it

- Ask a run about something narrated in an earlier adventure: that line comes back, and the closest line comes
  first.
- A line whose meaning could not be recorded is never returned by a question, but still appears in a recap.
- Ask for a recap and you get the newest lines in reading order, and nothing is encoded to answer it.
- Both refuse a run that does not exist; a run with no narration yet answers with nothing.

## Heads-up

- This sits on top of the previous sprint, not merged yet, so its review carries both until that one lands.
- Five lines is the default for both, changeable per call; the right number is for the phase where a Dungeon
  Master actually uses them.
- When the encoder is unavailable, asking a question fails rather than answering "nothing remembered": nobody
  should be told a run is empty when the machinery is down. Writing narration stays unaffected.

Brief: docs/intents/006-journal-memory/sprints/02-recall-by-meaning-and-recap/brief.md

## Verdict

Round 1: approve — a run can now be asked a question and answer with the narration closest to it in meaning from
anywhere in the run, including adventures it left long ago, and can be asked for its newest narration in reading
order when a game is picked up again; both from the command line, not yet from the Dungeon Master itself. Checked
against a real database: the closest line comes back first, a line whose meaning was never recorded is never
returned, a recap gives the newest entries oldest first without encoding anything, and a run that does not exist
is refused with a message.
