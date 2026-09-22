---
author: sprint
owner: human
created: 2026-09-22
updated: 2026-09-22
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/51
---
# Review: Sprint 06 — The run screen lists the adventures in order, marks which is next and says what the party is waiting for

## What changed
The run screen now shows the campaign's adventures below the party: one numbered row each, with its title, a teaser
and a word for where it stands. The next one to play says so — or says the party is not ready yet, and why. Starting
an adventure is not possible yet, and the button says as much by being greyed out.

## How to check it
- Open a run: under "Adventures", each adventure has a roman numeral, its title, a few lines of teaser and a badge.
- With nobody's character made yet, the first adventure reads "Waiting on party", a line beside the heading explains
  that every player needs a character first, and "Start adventure" is greyed out. Hovering it repeats the reason.
- Once every player has a character, that first adventure reads "Next up" instead; the button stays greyed out.
- Adventures further down read "Locked"; ones already played read "Done".
- Nothing on the screen can actually start an adventure — the button is inert by design for now.

## Heads-up
- The seeded content has one campaign with one adventure, so "Locked" and "Done" cannot be seen on the running site
  at all; they are covered by tests only. Worth a second campaign in the content set.
- The greyed-out button explains itself on hover but not on keyboard focus — a disabled button cannot take focus.
  The always-visible line beside the heading carries the same sentence, so nothing is hidden from a keyboard or
  screen-reader user.
- An adventure the API reports as already under way is drawn as the current one. Nothing in this intent can start an
  adventure, so it cannot happen yet; the word for that state is worth deciding when play actually ships.

Brief: docs/intents/007-initial-frontend/sprints/06-run-adventures-list/brief.md

## Verdict
Round 1: approve — opening a run now shows its adventures in order, each with a number, title, teaser and a word for
where it stands; the next one to play says so, or says the party is not ready yet and why, and starting one is visibly
not possible yet. One flaw found and fixed before merge: on a run where everyone had a character, the greyed-out
button still carried the "everyone needs a character first" explanation invisibly, so a screen-reader user could hear
a reason that no longer applied.
