---
author: sprint
owner: agent
created: 2026-09-24
updated: 2026-09-24
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/77
---
# Review: Sprint 06 — Narrow decisions and evidence-bound narration

## What changed
The storyteller now thinks in six small steps instead of one large one: reading what the player wants, making sense of a rule or of recalled play, settling which thing the player meant, judging an authored check, exit or fixture, choosing a monster's action, and choosing the world's reaction. Each step sees only the facts it needs and may only propose actions from its own short list; anything unsupported, or naming a creature, item or exit not in the scene, is thrown out and asked again, at most twice. The two knowledge steps may consult the rulebook and recall older play, at most three times per decision. Narration is a separate voice with no tools: it writes from the public picture and recorded outcomes, never from hidden clues, difficulties or private intent, and its draft is kept until safely recorded. Play is unchanged until sprint 08.

## How to check it
- In the merge request, one test has the storyteller propose an unsupported action and shows it refused, asked again and finally rejected.
- One test scripts four lookups and shows the storyteller stopping after three.
- One test inspects the words sent to the narrator and finds no hidden clue, difficulty or private intent, and no tools attached.

## Heads-up
The narrator speaks in one voice. The requirement map promises a selectable tone per run, but nothing applies one today; that is recorded as a proposal.

Brief: docs/intents/011-game-flow/sprints/06-decisions-and-narration/brief.md

## Verdict
Round 1: approve — the storyteller works in small, separately checked steps; an unsupported move or one naming something not in the scene is refused and asked again before being given up on; the narrator writes from the public picture alone with nothing it could look up, and a passage stays available until safely recorded. Known: the three-lookup limit applies per attempt, so a step asked again may look things up more often, which costs more per turn but changes nothing a player sees.
