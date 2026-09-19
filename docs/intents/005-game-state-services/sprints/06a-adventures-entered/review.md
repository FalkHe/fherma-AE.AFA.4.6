---
author: sprint
owner: agent
created: 2026-09-19
updated: 2026-09-19
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/30
---
# Review: Sprint 06a — an adventure is entered and its world takes its places

## What changed

A game's adventures are now entered one at a time, deliberately, and entering one puts the world in its places.
Until then everything the campaign declares exists but stands nowhere. On entry the adventure's creatures,
fixtures and loose items go where the content says they stand, every player character goes to the entry scene,
and what anyone carries stays with them. The transcript records that the adventure began.

## How to check it

- Entering answers the adventure: which one, that it is under way, and when it began.
- Greenhollow's cast then stands in its scenes and the character in the entry scene; carried items have not
  moved, and nothing else has either.
- The game's own status is unchanged — a game becomes *in progress* at its first narration.
- Entering while one is already under way is refused, and so is entering when nothing is left that this game
  has not done. There is no re-entering a finished adventure.

## Heads-up

- Sprint 06 was too big, so I split it the way you split 05: this half enters adventures. Using an exit —
  moving between scenes, ending an adventure, finishing the game — is 06b, which needs this one first.
- The refusal for "one is already under way" cannot happen in Greenhollow, which authors a single adventure:
  there the other refusal always comes first. It is tested against a made-up two-adventure campaign and will
  matter the day a campaign ships more than one.

Brief: docs/intents/005-game-state-services/sprints/06a-adventures-entered/brief.md

## Verdict

Round 1: changes requested — the check that entering an adventure puts the cast, the character and everything
carried in the right places is left out of the database test run and silently skips when no database is there,
so nothing would catch a future change that misplaces the world. Nothing proves yet that entering one adventure
leaves another adventure's creatures where they are — the thing a player would notice first once a campaign
ships more than one.

Round 2: approve — a game's adventures can now be entered one at a time, and entering one puts the whole
adventure in its places: its creatures and fixtures where the story puts them, the character at the way in,
everything carried still carried, and a line in the transcript saying it began. Both gaps from round 1 are
genuinely closed — the placement was broken on purpose and the check caught it, then broken again so a second
adventure's creatures were dragged along, and the new check caught that too.
