---
author: sprint
owner: agent
created: 2026-09-24
updated: 2026-09-24
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/78
---
# Review: Sprint 07 — One rule for what happens next

## What changed
The new flow now has its referee. One rule looks at the saved turn and a fresh picture of the scene and picks exactly the next thing that must happen, always in the same order: end the run if the hero is down or the story is over; finish an unresolved hit with its damage before anything else; wait for the player's roll or answer, or act on the answer just given; continue the action under way; run the fight, settling initiative once with the heroes winning a tie and giving each able enemy one go per round while skipping the fallen, the absent and the friendly; play out the world's reactions; narrate what is owed; and only then close the turn. A turn can never close while something is still owed. A player message that tries to override the Dungeon Master is refused in the Dungeon Master's own voice without consulting the model. The five workers that carry out each step exist as functions, including the pause that waits for the player and does nothing before it waits. They are not yet wired into the live game; sprint 08 does that.

## How to check it
- In the merge request, one table of turn states shows each picking the documented next step, including the fallen hero, the pending hit and the refused closure.
- One test runs a pause through a tiny throwaway graph, checks nothing was saved or rolled before it, and resumes it with the player's answer.
- Play a turn in the browser: nothing differs yet.

Brief: docs/intents/011-game-flow/sprints/07-scheduler-and-nodes/brief.md

## Verdict
