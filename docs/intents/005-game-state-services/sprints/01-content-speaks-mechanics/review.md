---
author: sprint
owner: agent
created: 2026-09-18
updated: 2026-09-18
url: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/merge_requests/24
---
# Review: Sprint 01 — the content speaks the mechanics' language

## What changed

An adventure can now end where the story ends it: the goblin lair has a way out that closes the adventure, and
every exit carries a name the game can refer to when a character takes it. A starting pack names the actual
items carried instead of reading as prose. The authoring rules say so, and Greenhollow follows them.

## How to check it

- Validating the shipped content passes, and the lair now offers "leave the hollow" as the way the adventure ends.
- An adventure whose final scene has no way out is refused; so are two ways out of one scene sharing a name.
- A pack listing something the campaign never defined, or a monster instead of an item, is refused.
- The Greenhollow character starts with five named items: knife, shield, lantern, twine, rations.

## Heads-up

- The pack was given the shepherd's knife, as the brief assumed. In the story that knife is Mira's evidence
  behind the bar, and the character is described carrying a spear — the same object now exists twice. The fix
  is to author a spear and leave the knife with Mira; noted for the backlog rather than decided here.
- A scene with no way out that is not the ending is a dead end, and nothing refuses it.

Brief: docs/intents/005-game-state-services/sprints/01-content-speaks-mechanics/brief.md

## Verdict

Round 1: changes requested — checks that pinned the Greenhollow adventure's own shape (who stands in which
scene, how many, what each carries, and which carried item opens which barrier) were deleted rather than
updated, so a later edit could quietly change the adventure's cast or layout with nothing objecting.

Round 2: changes requested — the scene-by-scene cast and the barrier checks are genuinely back, but nothing
checks what the figures in those scenes hold — the innkeeper's knife, the chief's cleaver, the two fleeces in
the sack — nor which shipped items count as weapons, so a later edit could leave the chief with nothing to
fight with and the adventure would still pass with every test green. Two rounds are the limit, so this stands
and the merge request is a draft: the sprint's own four criteria all pass, and the open item is coverage this
sprint deleted rather than anything the adventure does wrong.

Round 3: approve — everything the earlier rounds asked for is back. The checks on the Greenhollow adventure's
cast, on what each figure and container holds, and on which items count as weapons now say exactly what they
said before this sprint, and they bite: emptying the goblin chief's hands leaves the content valid but makes
the suite fail, which is precisely the silent change round 2 was about. The one open question, unchanged since
round 1, is the shepherd's knife in the starting pack, which follows the approved brief and is proposed for
the backlog.
