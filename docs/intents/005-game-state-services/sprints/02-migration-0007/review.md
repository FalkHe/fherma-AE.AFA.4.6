---
author: sprint
owner: agent
created: 2026-09-18
updated: 2026-09-18
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/25
---
# Review: Sprint 02 — the schema accepts the lifecycle this phase writes

## What changed

The stored game can now hold the states the coming sprints will put it in. A campaign run starts out merely
*set up* — the row exists, its character does not — then becomes ready, active, archived or finished, instead
of being called active from the first moment. A generated character no longer needs a template to point at.
The transcript accepts the twelve kinds of entry the game will write, not the five it began with. All of it
is one step forward that also steps back cleanly.

## How to check it

- A campaign run created without a state comes out *set up*; all five states are accepted and an invented
  one is refused.
- A character with no template is stored; the rules on hit points and on what may carry statistics still bite.
- Each of the twelve kinds of transcript entry is stored, and a thirteenth is refused.
- Stepping the schema back leaves it exactly as the previous step left it.

## Heads-up

- Stepping back restores the rule that every character must have a template, so it would fail on a database
  that already holds a generated one. Nothing generates characters yet; worth remembering once something does.

Brief: docs/intents/005-game-state-services/sprints/02-migration-0007/brief.md

## Verdict

Round 1: approve — the stored game now carries the whole run lifecycle: a run that only exists, one that is
ready, one being played, and the archived or finished ones; it accepts a character created without an authored
template and records all twelve kinds of transcript entry while refusing anything outside those sets. Stepping
the schema back leaves it exactly as it was before this change, checked against a real database and not just
the written instructions. The one thing to remember: stepping back would refuse to run once a generated
character exists, which cannot happen until character creation lands.
