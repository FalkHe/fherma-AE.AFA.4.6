---
author: sprint
owner: agent
created: 2026-09-19
updated: 2026-09-19
url: –
---
# Review: Sprint 05b — the run reports its cost and says when something is new

## What changed

A game can now say what it has cost — whole, and turn by turn — exactly, because the figures are decimals all
the way through rather than floating-point. It is a developer's number, so it is asked for with a command and
no address exposes it. Separately, a player's client can hold a connection open and be told when something new
has happened in their game. The message says only that; the client then re-reads the transcript the ordinary
way, so there is one way of reading it rather than two that could disagree.

## How to check it

- Asking a game's cost prints the total and one line per turn, entries belonging to no turn grouped last; a
  user who is not in the game is told it does not exist, and the command fails.
- No address anywhere answers with cost.
- The stream reports each new entry as it arrives, keeps the connection alive in between, and closes itself
  when the listener leaves or its time is up. Being refused looks like any other refusal.

## Heads-up

- Two faults in the test setup surfaced here and are fixed here, both able to hide a real failure: the tests
  reused one database connection across throwaway databases, so a test could pass or fail depending on what ran
  before it; and the fast test run skipped the database tests only when no database answered, making it depend
  on whether your dev stack happened to be up.
- This finishes sprint 05. Sprints 06 and 07 are unblocked.

Brief: docs/intents/005-game-state-services/sprints/05b-cost-and-live-signal/brief.md

## Verdict
