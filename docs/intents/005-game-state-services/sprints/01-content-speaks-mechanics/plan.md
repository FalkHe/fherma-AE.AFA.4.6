---
author: sprint
owner: agent
created: 2026-09-18
---
# Plan: Sprint 01

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | An exit is addressable by id and may end the adventure instead of leading on; a seed pack names item templates; the rules that assumed otherwise are restated, two added; the test fixture campaign is valid again | AC1–AC3: `to` required on a scene exit, refused on an ending one; terminal means "carries an ending exit", a scene with no exits refused; duplicate exit id refused; pack entry unknown or not an item refused | – |
| 2 | backend-python | The shipped `greenhollow` carries the ending exit, exit ids and four new item templates; its seed pack names them | AC4: `app content validate` passes the shipped tree; its pinned expectations follow | WI1, I1–I4 |
| 3 | backend-python | Authoring guide and module README describe ending exits, exit ids, the id-based pack and the two new rules; the worked example is valid under them | AC4: prose consistency with I3, I4 | I1–I4 |
| qa | qa | Black-box acceptance tests, one per criterion | below | – |

## Interfaces
- I1 `Exit`: `id: ContentId` (required) · `kind: Literal["scene","adventure_end"] = "scene"` · `to: ContentId | None = None` · `description: ProseText` · `condition: ProseText | None = None`. Invariant: `scene` ⇒ `to` set, `adventure_end` ⇒ `to` absent; a violation is `[SCHEMA]`, not a rule tag. `id` unique per scene only.
- I2 `SeedCharacter`: `inventory: list[ContentId] = []`.
- I3 Rules and tags (the message text is the contract docs and tests share):
  - R9 applies to `kind == "scene"` exits only; message unchanged.
  - R10 `adventures/<aid>.json: [R10] no scene reachable from entry_scene carries an adventure_end exit`; reachability first.
  - R11 skips exits with `to is None`. R14's reference set also holds every `seed_character.inventory` id.
  - R19 `adventures/<aid>.json: [R19] scene '<sid>': duplicate exit id '<eid>'`.
  - R20 `campaign.json: [R20] seed character inventory entry <i> names unknown object template '<id>'` and `campaign.json: [R20] seed character inventory entry <i> '<id>' is not an item`.
- I4 Content keys: exit ids `to-thornway`, `to-lair-maw`, `to-lair-hollow`; on `lair-hollow` `{"id": "leave-the-hollow", "kind": "adventure_end", "condition": null}`. New `item` templates after `stolen-fleece`, each `attacks: []`: `wooden-shield`, `hooded-lantern`, `coil-of-twine`, `rations` — thirteen, pinned order. Inventory `["shepherds-knife","wooden-shield","hooded-lantern","coil-of-twine","rations"]`. Fixture campaign (WI1): `mill-floor` gains an `adventure_end` exit, its inventory becomes `["rusty-key"]`.

## Acceptance tests (qa)
`backend/tests/content/test_acceptance_content_speaks_mechanics.py`, over temporary campaign trees plus the shipped one.
- AC1 → an ending exit without `to` loads; a scene exit without `to` is refused.
- AC2 → a last scene with an ending exit validates; one with no exits is refused.
- AC3 → two exits sharing an id are refused naming scene and id; a pack entry naming a creature or nothing is refused.
- AC4 → `app content validate` exits 0 over the shipped tree, `lair-hollow` ends the adventure.

## Order
Parallel: WI1, WI3, qa. Then: WI2.
