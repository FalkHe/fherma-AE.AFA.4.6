---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/64
---
# Review: Sprint 07 — review, save and the finished character

## What changed
The web creation loop is closed. When the sheet is complete, the page shows "One last look": the full sheet with name, race, class, level, alignment, hit points, armour class, speed, abilities with modifiers, skills, equipment, looks and story, the line "Saving makes it final for this run." and the buttons "Looks right, save" and "Change something". Saving returns the player to the run screen, where their card now shows the character with name, race and class, level, hit points, armour class and looks, marked Ready, the party line counts them and the first adventure reads "Next up". Taking the ready-made hero reaches the same review.

## How to check it
- Build a character on the creation page up to the Keeper's save question: the review appears with every field of the sheet and the two buttons.
- Click "Change something", ask for a different name, and the review comes back with the new name.
- Click "Looks right, save": you land on the run screen, the player card shows the character card with a Ready badge, "1 of 1 characters ready" and "Next up" on the first adventure, with no reload.
- On a fresh run click "Take Rosalind Thorn": her sheet appears as the review; saving puts her card on the run screen.

## Heads-up
- The saved character has no edit control, by decision.
- The run overview now returns the character as one nested object instead of a name; the API client was regenerated.
- The ready-made hero has no alignment, speed or skills of her own, so her review shows a dash there.

Brief: docs/intents/009-character-creation/sprints/07-review-save-and-character-card/brief.md

## Verdict
Round 1: approve — the last look shows the whole sheet, saving makes it final, and the run screen returns on its own with the character's card, the party counted ready and the first adventure next up; the ready-made hero reaches the same last look, "Change something" returns with the change made, and a failed save leaves the review with the tavern's line to try again.
