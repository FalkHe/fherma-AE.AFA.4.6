---
author: architect
owner: agent
created: 2026-09-17
updated: 2026-09-17
---
# Research: the general docs describe the model that exists

## Facts

**All 19 §7 citations still resolve to the text they describe.** `docs/general/` was last touched
2026-09-16 (`3e7658b`), before the §7 list landed 2026-09-17 (`07be52d`), so no line has moved and
nothing has been corrected already. Spot-verified each: item 1 `model.md:30`-`:32` (diagram nodes
`Playthrough`, `PlaythroughMember`, `Encounter`), 2 `:41`-`:47`, 3 `:81`, 4 `:92`-`:93`, 5 `:97`-`:102`
("one character per member" at `:102`), 6 `:107`, 7 `:161`-`:163`, 8 `:165`-`:169` (**the combat text
ends at `:169`; `:171` in the citation is the next heading — read the range as `:165`-`:169`**), 9
`:219`+`:223`, 10 `:301`-`:302`, 11 `:304`, 12 `:306`, 13 `:312`-`:314`; 14 `architecture.md:23`-`:24`,
15 `:76`+`:78`; 16 `glossary.md:16`+`:64`, 17 `:51`+`:58`-`:61`; 18 `app-vision.md:50`+`:54`; 19
`requirement-map.md:28`+`:32`.

**One entity use is not on the list but AC1's grep catches it:** `model.md:57`, "objects hanging off the
**Playthrough**" — capitalised, entity sense, same fact as item 6. Legal prose uses that must survive:
`model.md:60` ("survives every playthrough"), `architecture.md:45` ("start of a playthrough").
`architecture.md:72` (`start_combat()` / `end_round()`, "Initiative and turn tracking") is **not** in
§7 — roadmap `:388` assigns it to phase 8; leave it.

**Module doc format** (`docs/modules/content.md:1`-`:9`): no frontmatter, `# <name> — <subtitle>`, a
framing paragraph, then numbered `## n. <title>` sections, tables for field lists. **Index row**
(`docs/README.md:19`-`:23`): a `## Modules` table, columns `Doc | Contents`, one row
`| [modules/content.md](modules/content.md) | <one line, no trailing period> |`.

**AC5's source of truth** is `backend/app/modules/playthrough/README.md:1`-`:67` (five tables, columns,
constraints) plus `models.py:25,48,72,108,179` (`CampaignRun`, `CampaignRunMember`, `AdventureRun`,
`GameObject` → table `objects`, `Event`). Surface today: none — "No service, route, schema or CLI yet"
(`README.md:66`).

**Roadmap wording to close, verbatim targets:** `Stage-01/README.md:315` ownership (membership row,
upheld), `:316` adventure progress (separate entity, D10), `:317` where the state models live
(`playthrough`, D14), `:318` event cost (stored per event, D4); `:385` the conditional ownership row,
`:386` the conditional `AdventureRun` row. Each is one table row in `## 7. Open-decisions register`
(`:302`) and the correction register respectively; closing means editing those six rows only.

## Work items

**Splitting the five general docs does not help.** Items 1–19 are one argument in one voice — the
diagram at `model.md:30` and the glossary entries at `glossary.md:58` state the same fact twice — and
model.md alone carries 13 of 19. Two writers there would diverge faster than one writer costs.

- **WI1 — the five general docs.** `model.md` (items 1–13 + `:57`), `architecture.md` (14–15),
  `glossary.md` (16–17), `app-vision.md` (18), `requirement-map.md` (19). One agent, one pass.
- **WI2 — `docs/modules/playthrough.md` + the `docs/README.md:23` index row.** Different source
  material (the backend README), different file, genuinely parallel with WI1.
- **WI3 — the roadmap closure.** Six rows, mechanical, parallel. Nothing else in `roadmap/` is touched.

`make lint` (Makefile:73) runs ruff and ESLint only; no markdown is linted, so AC7 is satisfied by not
touching code.

## Interfaces

Shared vocabulary — every work item uses these exact strings:

| Concept | Write | Never |
|---|---|---|
| Container entity | `campaign_runs` / **campaign run** | Playthrough, CampaignRun in prose |
| Adventure entity | `adventure_runs` / **adventure run** | AdventureRun |
| Membership | `campaign_run_members` | playthrough_members, PlaythroughMember |
| The other three | `objects`, `events`; `objects` rows are **creature**, **item**, **fixture** | Object/Event as entity nouns |
| Module | the `playthrough` module — the activity, not an entity | — |
| Combat, turn order, initiative | "**deferred to the DM-turn phase**; this phase builds no combat state" | deleted silently, "planned", "TODO" |
| Position | "**Position belongs to the creature, not the party**: the pair `(adventure_run_id, scene_id)` on its own `objects` row. No row claims a party position." | party position, position on the adventure run |
| Several characters | "the model lets a user control several characters in one campaign run; Stage-01 gameplay assumes one" | one character per member |
| Seed player character | "**seed player character** — the authored fixture a campaign run instantiates the player's creature from until the generation agent lands" | — |

## Open questions

All technical; none product-visible.

1. **`model.md:57`** is an entity use of `Playthrough` that §7 does not enumerate, while AC1 requires
   `Playthrough` to grep clean. Recommend applying it as part of item 6 and noting it in `progress.md`.
2. **The Purge row** (item 11, `model.md:304`): §7 says out of Stage-01 scope and D3 deletes nothing,
   but not whether to delete the row or mark it deferred. It also names `encounters` and
   `journal entries`. Recommend deleting the row and folding `:306` ("There is no
   `DELETE /playthroughs/{id}`") into one sentence under D3: nothing is ever deleted.
3. **Known gaps renumber** once gap 1 (`:312`) goes — gaps 2–4 become 1–3. Nothing cites them by number.
4. **No §7 item is unapplicable.** Every one matches the landed schema, including item 7 (position
   landed as `(adventure_run_id, scene_id)`) and item 5 (`objects.member_id`, no unique index).
   `JournalEntry` stays in the diagram as phase-6 design with its owner renamed to the campaign run.
