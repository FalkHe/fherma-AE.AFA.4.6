---
author: sprint
owner: agent
created: 2026-09-21
updated: 2026-09-21
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/37
---
# Review: Sprint 01 — narration is remembered on write

## What changed

The DM's long-term memory starts here: every line the DM narrates is now encoded by meaning as it is written,
so a later search can find it by what it was about rather than by the words in it. The player's own typed text
is deliberately not encoded — narration always says back what the player did, so the player's intent reaches
memory that way. What the encoding costs is booked on the same transcript line, so the run's cost report
already counts it. Nothing can be searched yet; that is the next sprint.

## How to check it

- Writing a line of narration into a run from the command line stores it along with its meaning and the name of
  what encoded it, and the tokens and cost of encoding it land on that same line.
- Writing a player's action the same way stores the line and nothing else — no encoding, and no call made.
- With the encoder broken, the narration is still written and the command still reports success; only that one
  line stays unfindable later, and the player would notice nothing.

## Heads-up

- Two of last sprint's checks stated the transcript's columns exactly as they stood, so widening the transcript
  broke them; they were restated to allow the two new ones. What they guard — that a fight leaves no state
  behind anywhere — is unchanged.
- A line of narration that is empty is stored with no meaning attached and no complaint, since there is nothing
  worth encoding.

Brief: docs/intents/006-journal-memory/sprints/01-narration-remembered-on-write/brief.md

## Verdict

Round 1: approve — every line the Dungeon Master narrates is now stored together with a record of what it means,
and what producing that record costs is booked onto the same line of the run's cost report. A player's own typed
text is stored exactly as before with nothing extra added, and when the encoder fails the narration is still
written and the run carries on untouched — all three confirmed by writing lines into a real run. Nothing can be
searched yet; that is the next sprint by design.
