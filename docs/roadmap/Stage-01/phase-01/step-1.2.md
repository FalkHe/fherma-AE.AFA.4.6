---
title: "Step 1.2 — The authoring guide and the documents this phase invalidates"
stage: 1
phase: 1
step: 1.2
status: spec
created: 2026-09-11
---

# Step 1.2 — The authoring guide and the documents this phase invalidates

Write `docs/modules/content.md` — the schema reference an agent can author a
conformant campaign from **alone** — add its row to the documentation index, and
apply every correction phase 1 owns to the general design documents.

Read together with [`shared-knowledge.md`](shared-knowledge.md), which is the
**binding phase contract** and the source of every field name, constraint, rule
number and worked example this guide states. Where this file and that file
disagree, that file wins.

Runs **in parallel with step 1.1**. That step touches only `backend/`; this step
touches only `docs/`. Neither may edit the other's files.

## 1. Scope

In scope: one new document, one index row, seven corrections across three
general documents, and three rows added to the stage README — two to its §9
doc-correction register, one to its §7 open-decisions register.

Out of scope, and a deviation if it appears:

- **Any file under `backend/`.** In particular
  `backend/app/modules/content/**` — step 1.1 is writing it right now — and
  `backend/content/**`, which step 1.3 authors.
- `docs/general/glossary.md`. Its *Definition* entry is still accurate, and the
  *seed player character* term is assigned to phase 5 by stage README §9.
- Any correction the stage register assigns to another phase. Phase 1 owns the
  rows of §3 below and nothing else.
- Writing a content generator, a prompt asset, or anything executable. Stage
  README §5 fences the LLM content-generation CLI out of Stage-01: **the
  document is the deliverable.**

## 2. Environment you will meet

- The Docker stack is **down**; nothing in this step needs it running.
- There is no `.env` file, only `.env.dist`, which is owner-only. This step runs
  no command that reads it.
- `docs/modules/` **does not exist** — create the directory.
- `docs/README.md` currently says, under *Modules*:
  `*None yet — the first module doc lands with the first subsystem.*`
- `backend/app/modules/content/` may or may not exist yet depending on step
  1.1's progress. **Do not read it and do not wait for it.** The guide is written
  from the phase contract, which is complete; if the guide were written from the
  implementation, step 1.3 could not falsify it.

## 3. Files this step creates or edits

All owned by **backend-dev**.

| File | Change |
|---|---|
| `docs/modules/content.md` | **New.** The authoring guide (§4). |
| `docs/README.md` | One row under *Modules* (§5). |
| `docs/general/model.md` | Five corrections (§6). |
| `docs/general/architecture.md` | One correction (§6). |
| `docs/general/requirement-map.md` | One correction (§6). |
| `docs/roadmap/Stage-01/README.md` | Two rows added to §9's register and one to §7's (§7). |

`docs/roadmap/Stage-01/README.md` is the **only** file phase 1 edits outside the
phase directory and the `content` module. Add rows to the §9 and §7 tables;
change nothing else in that document.

## 4. `docs/modules/content.md` — the authoring guide

The falsifiable claim this document makes is: **an agent given this file and
nothing else can author a campaign that `app content validate` accepts.** Step
1.3 tests exactly that. Write for that reader.

It must contain, and in a form an author can act on:

1. **What content is and what it is not.** One short paragraph: hand-authored
   static JSON in git, read-only at runtime, referenced by a run through a
   campaign id plus a pinned version. Not a database, not a script, not
   generated.
2. **The directory layout** — phase contract §4, with real example paths.
   Include that content lives at `backend/content/`, that only `*.json` files
   are considered, and that a missing `adventures/` / `scenes/` / `definitions/`
   directory is treated as empty.
3. **Versioning** — a version is a `v<n>` directory; content is extended by
   copying the tree to `v2` and editing there, never by editing a published
   version in place, because a run pinned to `v1` must stay reproducible.
4. **The casing and naming rules** — snake_case JSON keys identical to the
   field names; ids are lowercase kebab-case; the key is `character_class`, not
   `class`; the key is `armour_class`, not `armor_class`. State each of these
   as a rule, because each is a mistake an author makes by default.
5. **Every model and every field** — phase contract §3, in that order. For each
   field: the JSON key, its type, whether it is required, its default if any,
   and one sentence on what it is for. Nothing may be omitted as "obvious".
6. **Every constraint that actually rejects a file** — `extra="forbid"` (an
   unknown key is an error, not an ignored extra); the id pattern
   `^[a-z0-9]+(-[a-z0-9]+)*$`; that every prose string is stripped and must then
   be non-empty, so `"   "` is rejected; every `min_length`, `ge` and `le` bound
   given in phase contract §3.
7. **The rule list** — phase contract §11 reproduced in full, with the `[R<n>]`
   tags, so an author who sees `scenes/x.json: [R11] …` can look up what R11
   requires. State which rule is checked by the CLI rather than the loader (R3).
8. **The message grammar an author will see** —
   `<path>: [<TAG>] <detail>`, with `READ`, `SCHEMA` and `R2`…`R18` explained
   (R1 carries no tag of its own — it is reported as `[READ]` or `[SCHEMA]`),
   and the `app content validate` exit codes.
9. **The complete worked example** — phase contract §4.1, **reproduced
   verbatim**, all five files. This is the part an author copies from, so it
   must be byte-faithful; a divergence here is a defect.
10. **The two rules a generator gets wrong by default**, stated in these words
    and given their own heading:
    - **A scene is facts, intentions and consequences, never a script.** Write
      what is true, what the creatures present want, and what follows from
      plausible player action. Never write what the player does, never write a
      branch, never write dialogue the player must hear.
    - **An exit condition is prose the agent judges, never a flag, a variable or
      a comparison.** There is no flag store in this system, so there is nothing
      to compare against. Write `"the bar has been broken, forced, or lifted
      from outside"`, never `"alarm_raised == false"`.
11. **What the schema deliberately does not carry**, so an author does not try
    to add it: no items and no fixtures (creatures only); no level, no
    proficiency bonus, no skills, no player attacks — a monster's `to_hit` is
    the complete bonus and every other check resolves on the raw ability
    modifier; no portrait; no speed and no challenge rating.
12. **A short authoring checklist** an author can run down before validating:
    every scene reachable from `entry_scene`; at least one scene with no exits;
    every definition referenced by at least one scene; no definition placed
    twice in one scene; definition names unique.

Keep the repository's documentation conventions (`docs/README.md`): state the
current behaviour, not the journey to it; where something is not obvious, say
**why** in one clause.

## 5. `docs/README.md`

Replace the *Modules* section's placeholder line with a table in the same shape
as the *General* table, carrying one row:

| Doc | Contents |
|---|---|
| [modules/content.md](modules/content.md) | The adventure-content schema, its directory layout and versioning, and the authoring guide |

## 6. The corrections

Apply each exactly as described. Do not rewrite surrounding prose beyond what
the correction requires.

| # | File | Section | Correction |
|---|---|---|---|
| C1 | `docs/general/model.md` | *Static files* | The content root is `backend/content/`, not `content/`. Give the reason in one clause: the Dockerfile copies `backend/` and compose bind-mounts it, so the path is identical in the image, under the dev bind mount and on the host, with no configuration. |
| C2 | `docs/general/model.md` | *Static files* | `npcs/` and `monsters/` become one `definitions/` directory holding one `Definition` entity, which **always** carries a stat block. The same document already rules there is no npc/monster split; this is that ruling applied. |
| C3 | `docs/general/model.md` | *Static files* | The scene-field line becomes the pinned set: `truth[]`, `npc_intent?`, `consequences[]`, `hidden[]`, `creatures[]`, `exits[]` — **a list, not a map** — and `pressure?`. |
| C4 | `docs/general/model.md` | *Static files* | `campaign.json` also carries the **seed player character**, and each adventure file carries a prose **`intro`** and an **`entry_scene`**. |
| C5 | `docs/general/model.md` | *Content lives in git, runs pin a version* | State the mechanism: a version is a `v<n>` directory under the campaign, served whole by the loader, never edited in place. |
| C6 | `docs/general/architecture.md` | *System components* → **Adventure content** | Strike "Authored by an LLM once through a `generate_adventure` CLI that prompts with the SRD and enforces the schema". Content is **hand-authored**, validated by `app content validate`, and reviewed as a diff. Leave the rest of the bullet intact. |
| C7 | `docs/general/requirement-map.md` | *Task requirements*, row 3 | State the player-capability reading of stage README §8: every **player** capability has a surface; operator capabilities such as content validation are CLI-only by design, because putting developer machinery in the player UI is exactly what optional task Medium-8 penalises. One sentence in the row or immediately beneath the table — phase 11 makes the full argument. |

C1–C5 land in one edit of the *Static files* section; do not fragment it.

## 7. The two stage-register rows

Phase 1 adds **three** rows to `docs/roadmap/Stage-01/README.md`: two to §9's
doc-correction register and one to §7's open-decisions register. Change nothing
else in that document.

### 7.1 Two rows for §9

Stage README §9 declares itself the single home for doc corrections, and phase 1
found corrections it does not list. Add exactly these two rows to that table:

| Contradiction | File | Owning phase |
|---|---|---|
| The static-file tree's content root, the `npcs/` + `monsters/` split, the scene-field line, the missing `intro` / `entry_scene` / seed character, and the unstated version mechanism — enumerated in `roadmap/Stage-01/phase-01/shared-knowledge.md` §9.2 | `general/model.md` | 1 |
| The tool table's `get_monster(name)` row — with one `Definition` entity the binding is id- or name-addressed over `definitions`, and its final name and argument are phase 8's to pin | `general/architecture.md` | 8 |

### 7.2 One row for §7

Phase contract §10.3 records an obligation that is a **note, not a control**: if
nothing carries it forward, phase 8 ships a leak that phase 9 discovers. §7 is
the register for exactly this — recorded, not settled, settled in the owning
phase's step spec. Add exactly this row to §7's table:

| Open decision | Owning phase |
|---|---|
| **How `hidden` and `Secret.dc` are projected out of any scene-derived tool result** before it reaches the visible trace. Content carries DM-only secrets and their difficulty; a tool result that passes a `Scene` through unfiltered leaks both, and "the fact that a roll happened is not a tell" fails. Recorded by phase 1 (`roadmap/Stage-01/phase-01/shared-knowledge.md` §10.3) | 8 |

## 8. Acceptance criteria

Numbered, each provable or refutable by a QA agent without reading
`backend/app/modules/content/`.

1. `docs/modules/content.md` exists and `docs/modules/` contains no other file.
2. `docs/README.md`'s *Modules* section is a table with a row linking
   `modules/content.md`, and the string "None yet" no longer appears in the
   file.
3. The link `modules/content.md` from `docs/README.md` resolves to an existing
   file, as does every relative link inside `docs/modules/content.md`.
4. The guide documents **every** model of phase contract §3 by name:
   `Abilities`, `Attack`, `StatBlock`, `Definition`, `Secret`,
   `CreaturePlacement`, `Exit`, `Scene`, `Adventure`, `SeedCharacter`,
   `Campaign`. (`LoadedCampaign` is an in-memory aggregate and need not appear.)
5. Every field name of phase contract **§3.1–§3.11** appears in the guide,
   spelled exactly as it is spelled there — checkable mechanically field by
   field. §3.0 and §3.12 are excluded: the first is a conventions section and the
   second is `LoadedCampaign`, an in-memory aggregate no author writes.
6. The guide states `character_class` (not `class`) and `armour_class` (not
   `armor_class`) as explicit rules, and the string `"\"class\":"` appears
   nowhere in it. **`armor_class` is not a forbidden string** — the rule itself
   has to quote the spelling it rejects, and §4 item 4 requires exactly that.
7. The guide reproduces phase contract §11's rule table with all eighteen
   `[R<n>]` tags, and marks R3 as the CLI-level check.
8. The guide reproduces the worked example of phase contract §4.1 in full — all
   five files — and every JSON block in it is parseable JSON.
9. The guide states the message grammar `<path>: [<TAG>] <detail>`, explains
   `READ`, `SCHEMA` and `R<n>` (and that R1 carries no tag of its own), and
    gives the `app content validate` exit codes
   `0` and `1` with their conditions.
10. The guide contains, under its own heading, the sentence **"A scene is facts,
    intentions and consequences, never a script."** and the sentence **"An exit
    condition is prose the agent judges, never a flag, a variable or a
    comparison."**
11. The guide states that content declares no items and no fixtures, and that
    there is no level, proficiency bonus, skill list or authored player attack.
12. The guide contains an authoring checklist covering: reachability from
    `entry_scene`, at least one scene with no exits, every definition referenced,
    no duplicate placement in a scene, unique definition names.
13. `docs/general/model.md`'s *Static files* section shows the content root as
    `backend/content/`, shows a single `definitions/` directory, shows no
    `npcs/` or `monsters/` directory, and shows the scene-field set of C3.
14. `docs/general/model.md` states that `campaign.json` carries the seed player
    character and that an adventure carries `intro` and `entry_scene`.
15. `docs/general/model.md`'s *Content lives in git, runs pin a version* section
    states the `v<n>` directory mechanism.
16. `docs/general/architecture.md` no longer contains the string
    `generate_adventure`, and its *Adventure content* bullet says the content is
    hand-authored and validated by `app content validate`.
17. `docs/general/requirement-map.md`'s requirement-3 entry states the
    player-capability reading and names content validation as an operator
    capability.
18. `docs/roadmap/Stage-01/README.md` §9's table contains the two rows of §7.1,
    §7's table contains the row of §7.2, and the document is otherwise unchanged
    (provable from the diff).
19. `docs/general/glossary.md` is unchanged.
20. No file under `backend/` is created or modified by this step (provable from
    the diff).
21. **The falsifiable criterion.** Step 1.3's author works from
    `docs/modules/content.md` alone, without opening
    `backend/app/modules/content/`, and the campaign they produce passes
    `app content validate` on the first run after the owner's prose review. Any
    field name, constraint or rule the author had to guess at is a defect in
    this guide and is fixed in the guide, not worked around in the content.

Criterion 21 is verified in step 1.3 and is the reason this step exists.

## 9. Static checks the dev agent runs

This step lands no code, so there is nothing to lint, type-check or boot. The
checks are:

```bash
git diff --stat                 # must show only docs/ paths
```

- Every changed path is under `docs/`.
- Every JSON block in `docs/modules/content.md` parses — verify each one, e.g.
  by pasting it through `python -m json.tool`.
- Every relative link in the touched documents resolves.

**Do not run pytest** — the suite belongs to qa-backend. There is no ruff, no
type check and no boot check for a documentation-only step.

**A noted carve-out from the verification split.** Acceptance criteria 3 and 8
ask qa-backend to re-check link resolution and JSON parseability, which the dev
agent has just checked above. `.claude/CLAUDE.md` normally forbids QA
re-authoring a dev agent's static checks; this step is the exception, because a
documentation-only step has no other QA surface at all. Accepted deliberately,
not by accident.

## 10. The parallelisation split

| Agent | Owns |
|---|---|
| backend-dev | `docs/modules/content.md`, `docs/README.md`, the three `docs/general/*` corrections, and the three rows in `docs/roadmap/Stage-01/README.md` (§7). Nothing else. |
| qa-backend | Verification of criteria 1–20 against the landed documents. Criterion 21 is verified in step 1.3. |

**This step must not touch `backend/app/modules/content/` — step 1.1 owns it and
is editing it concurrently.**

## 11. Deviation clause

**Zero deviations from this spec and from
[`shared-knowledge.md`](shared-knowledge.md).** If the phase contract turns out
to be ambiguous or self-contradictory while you are writing the guide from it —
which is exactly what this step is good at exposing — **stop and report it**.
Do not resolve the ambiguity by reading `backend/app/modules/content/`, and do
not invent a field, a constraint, a rule or a default that the phase contract
does not state.
