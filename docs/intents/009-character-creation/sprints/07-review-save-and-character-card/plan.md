---
author: sprint
owner: agent
created: 2026-09-23
---
# Plan: Sprint 07

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 0 | backend-python | `CharacterRead` gains race, class, level, appearance; the run overview's member entry carries `character: CharacterRead | null` instead of `characterName`; `show_sheet(ready_made=True)` flags the draft and `creation_progress` renders the seed as a saveable review; regenerated spec + client | the overview shows the four facts for a member with a character and null without; the ready-made preview yields step review with canSave and the seed's data | – |
| 1 | frontend | `ReviewPanel` as a state of the creation page, save → invalidate overview → navigate to the run, `CharacterCard` in the player card, locale keys, READMEs, six tests | AC1 a review reply renders every field · AC2 "Change something" brings the transcript back and posts its text, "Looks right, save" posts its text · AC3 `saved: true` lands on the run and refetches the overview · AC4 the player card shows name, race/class, level, HP, AC, looks, no create button, party line counts · AC5 an `error: true` save reply keeps the review with the in-voice line · AC6 copy equals the locale values | I1 (codes against it; final typecheck after WI0's client) |

No qa work item (backlog: black-box tests only in sprint 05).

## Interfaces
- I1: everything under `research.md → Interfaces` — the widened `CharacterRead`, `CampaignRunMemberRead.character`, the `ready_made` draft flag and `creation_progress(draft, *, seed, seed_items)`, `useCreationChat.canSave`, `ReviewPanel`/`CharacterCard` props, the exact button texts ("Looks right, save" / "Change something"), locale keys. Technical decisions 1–6 are binding.

## Order
Parallel: WI0, WI1 (WI1 typechecks once WI0's client lands). Then gates.
