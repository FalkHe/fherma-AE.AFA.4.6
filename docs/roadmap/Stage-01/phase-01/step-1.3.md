---
title: "Step 1.3 — The first campaign"
stage: 1
phase: 1
step: 1.3
status: spec
created: 2026-09-11
revised: 2026-09-11
human_in_the_loop: true
---

# Step 1.3 — The first campaign

**In the P1-D20 rework this step is a mechanical migration, not an authoring
step.** `greenhollow/v1` is already authored, already owner-accepted and already
in the tree. This pass folds each `scenes/<id>.json` body into the adventure's
`scenes` array, deletes those files and the `scenes/` directory, and proves the
re-shaped tree loads and validates. **Not one word of prose changes.** §3 is the
binding rule for how.

The step's original purpose — author the shipped campaign from
`docs/modules/content.md` alone and let that falsify the guide — was served and
passed in the first pass. It is recorded here because it is what the step means
the *next* time a campaign is authored; it is not re-run now (§3, criteria 21
and 23).

**Human in the loop, already satisfied.** The owner read and accepted this
campaign's prose in the first pass. Because the migration changes no prose, that
acceptance carries; criterion 23 is closed, not re-measured.

**Depends on steps 1.1 and 1.2.** Both must have landed in their re-worked
form — in particular `Adventure.scenes: list[Scene]` must be live, or the
migrated tree cannot validate.

## 1. Scope

In scope:

- `backend/content/campaigns/greenhollow/v1/**` — the shipped tree, migrated to
  the one-file-per-adventure layout, **including the deletion** of the four
  scene files and the now-empty `scenes/` directory (§5).
- `backend/tests/content/**` — qa-backend's unmocked shipped-tree tests,
  re-authored against the amended contract.
- `docs/modules/content.md` — **only** to fix a defect the migration exposed
  (§7). In a pure migration there should be nothing to fix.

Out of scope, and a deviation if it appears:

- Any change to `backend/app/modules/content/**`. If the content cannot be
  expressed within the schema the guide describes, that is a finding to report,
  not a schema change to make.
- A second campaign, a second adventure, a second content version. Stage README
  §5 fences all three out: one campaign, one adventure is the stated initial
  content set.
- SRD text reproduced verbatim. The campaign is *SRD-flavoured* — it uses the
  vocabulary and the shape of 5e — but every stat block, name and line of prose
  is written for this repository. Do not paste SRD monster entries.
- **Any change to the prose, the ids, the stat blocks, the numbers or the
  structure of the story.** This pass moves text between files and deletes
  files. Improving a sentence, renaming a scene, reordering `truth` entries or
  "tidying" a stat block all invalidate the owner's acceptance and are
  deviations.

## 2. Environment you will meet

- The Docker stack is **down**.
- **`.env` exists**, copied from `.env.dist`; `.env.dist` stays owner-only and
  must not be edited. It has to exist: without it `app content validate` raises
  a `ValidationError` before doing any work, and `docker compose run app-cli`
  cannot start at all. If it is missing, run `cp .env.dist .env`.
- Alembic head is `0001`. **This step adds no migration.**
- `backend/app/modules/content/` exists and has been re-worked to P1-D20 by
  step 1.1: `Adventure.scenes` is `list[Scene]`, and the rule set is R1–R16.
- `docs/modules/content.md` exists and has been re-worked by step 1.2.
- `backend/content/campaigns/greenhollow/v1/` **exists in the pre-amendment
  layout**: `campaign.json`, `adventures/goblins-of-greenhollow.json` whose
  `scenes` is a list of four ids, `scenes/` holding `village-green.json`,
  `thornway.json`, `lair-hollow.json` and `lair-maw.json`, and `definitions/`
  holding `mira.json`, `goblin.json` and `goblin-boss.json`.
- **Running `app content validate` right now exits `1` with four stderr
  lines**: a `[SCHEMA]` entry on `adventures/goblins-of-greenhollow.json` — the
  adventure still carries a list of scene ids — and then an `[R14]` for each of
  `definitions/goblin-boss.json`, `definitions/goblin.json` and
  `definitions/mira.json`, because the dropped adventure contributes no scenes
  and nothing else references them (phase contract §11's drop block). **All four
  lines are the starting state, and all four clear together** when the migration
  lands: making this command exit `0` is this step's headline evidence.
- `backend/tests/content/test_shipped_tree.py` exists and is currently red for
  the same reason. That is expected (phase contract §8).

## 3. The migration rule

**This pass is mechanical and its correctness is checkable by eye.** For the one
adventure:

1. For each id in `adventures/goblins-of-greenhollow.json`'s `scenes` list, in
   the order the list already has, take the **entire object** in
   `scenes/<id>.json` and append it to a new `scenes` array in the adventure
   file, replacing the id list.
2. Keep every scene's `id` key. It is how exits, `entry_scene`, runs and
   `LoadedCampaign.scenes` address it, and it is what R8 now polices.
3. Delete the four scene files and the `scenes/` directory.
4. Change nothing else — not a character of prose, not a number, not an id, not
   the order of anything.

**The falsifiable property of this pass**: concatenating the scene objects out
of the migrated adventure file reproduces the four deleted files exactly, key
for key and string for string. `git show` of the deleted files is the reference.

**The first pass's restricted-reading device does not apply here.** In the first
pass the authoring half was dispatched with `docs/modules/content.md` alone, so
that the campaign it produced would measure the guide's completeness (step-1.2
criterion 23). There is no fresh authoring in this pass and therefore nothing to
measure: **this pass is dispatched normally**, with `shared-knowledge.md`, and
the whole of this file including §6. Withholding §6 now would only hide the
checklist from the agent doing the move.

Consequently **criteria 21 and 23 are closed from the previous pass and are not
re-measured** — 21 because no authoring happened, 23 because the prose the owner
accepted is byte-identical after the move.

## 4. The authoring brief

**Already satisfied by the landed campaign; carried here as the verification
checklist for the migration and as the brief for any future authoring pass.**
Every item below must still be true of the migrated tree — a migration that
loses one of them has moved something it should not have.

**A classic starter: a village, a trail and a goblin lair.** Chosen by the owner
because it exercises every feature of the schema with no licensing worry:

- **A patron NPC in the village** who hires the player. A talker, not a fighter
  — a definition whose `stat_block.attacks` is `[]`.
- **A trail** between the village and the lair: an outdoors scene with something
  hidden on it.
- **A lair**: the goblins' place, where a fight is the likely outcome.
- **A villain** — the goblin boss — who **can escape and return in a later
  adventure**. Definitions are campaign-scoped precisely so that a named
  antagonist survives an adventure boundary; the escape is written as a
  `consequences` entry, not as a mechanic, because there is no flag store.

Hard requirements, each checkable:

| # | Requirement |
|---|---|
| B1 | Exactly one campaign, id **`greenhollow`**, at exactly one version, **`v1`** |
| B2 | Exactly one adventure. Its id and title are yours |
| B3 | **At least three scenes**, all inside that one adventure's file |
| B4 | **At least one terminal scene** — one with no exits — and the adventure's entry scene is not it |
| B5 | **Every scene reachable** from the entry scene by following exits |
| B6 | **At least one definition placed in two different scenes** — the reuse a campaign-scoped definition exists for |
| B7 | **At least one definition that cannot fight** (`attacks: []`) and **at least one that can** (a non-empty `attacks` list) |
| B8 | **At least two `hidden` entries**, in at least two different scenes, each with an authored `dc` and a prose `discovered_by` |
| B9 | **At least one exit carrying a `condition`** — prose the DM judges, naming no flag, variable or comparison — **and at least one exit with no condition**, so both shapes ship |
| B10 | **At least one placement with `count` greater than 1** |
| B11 | A seed player character whose gear and background suit this campaign |
| B12 | A `consequences` entry somewhere that makes the villain's escape a possible outcome |

Prose standards the owner will read for:

- **A scene is facts, intentions and consequences, never a script.** No
  narration to be recited, no branch, no "the player then…". Write what is true,
  what the creatures want, and what follows from plausible action.
- **The DM improvises inside the truth.** A scene that leaves the DM nothing to
  decide is a defect even when it validates.
- **The player never has to know the rules.** Prose is for a reader who has
  never played; `discovered_by` says what a character *does*, not only which die
  to roll.
- English, British spelling, present tense for scene truth.

## 5. Files this step creates or edits

| File | Owner | Action |
|---|---|---|
| `backend/content/campaigns/greenhollow/v1/campaign.json` | backend-dev | **Unchanged.** Expect no diff. |
| `backend/content/campaigns/greenhollow/v1/adventures/goblins-of-greenhollow.json` | backend-dev | **Modified.** `scenes` becomes the four scene objects inline, in the order the id list had. Everything else unchanged. |
| `backend/content/campaigns/greenhollow/v1/scenes/village-green.json` | backend-dev | **Deleted.** |
| `backend/content/campaigns/greenhollow/v1/scenes/thornway.json` | backend-dev | **Deleted.** |
| `backend/content/campaigns/greenhollow/v1/scenes/lair-hollow.json` | backend-dev | **Deleted.** |
| `backend/content/campaigns/greenhollow/v1/scenes/lair-maw.json` | backend-dev | **Deleted.** |
| `backend/content/campaigns/greenhollow/v1/scenes/` | backend-dev | **Deleted** — the directory itself must be gone, not left empty. |
| `backend/content/campaigns/greenhollow/v1/definitions/*.json` | backend-dev | **Unchanged.** Expect no diff on any of the three. |
| `docs/modules/content.md` | backend-dev | **Only** if the migration exposed a guide defect (§7) |
| `backend/tests/content/**` | qa-backend | The unmocked shipped-tree tests, re-authored (§6, criteria 15–19) |

`git status` after the move must show exactly one modified content file, four
deletions, and nothing else under `backend/content/`. **A rework whose file list
carries no deletion is how a stale `scenes/` directory survives into phase 5.**

**qa-backend must not write into `backend/content/`.** If the agent that proves
the tree valid is also the agent that authored it, the phase's central evidence
is circular. backend-dev must not write into `backend/tests/`.

## 6. Acceptance criteria

Numbered, each provable or refutable without reading
`backend/app/modules/content/`.

### The shipped tree

1. `backend/content/campaigns/greenhollow/v1/campaign.json` exists, and
   `backend/content/campaigns/` contains exactly one campaign directory, which
   contains exactly one version directory, named `v1`.
2. `campaign.json`'s `adventures` list has exactly one entry, and
   `adventures/` contains exactly one `*.json` file.
3. That adventure file's `scenes` list holds at least three scene objects, each
   with its own `id`, and no two share an `id`.
4. The version directory contains **no `scenes/` directory**: the whole
   adventure, scenes included, is one file.
5. At least one scene has `exits` absent or `[]`, and it is not the adventure's
   `entry_scene`.
6. Every scene is reachable from `entry_scene` by following `exits`, ignoring
   conditions — checkable by walking the JSON alone.
7. Some definition id appears in the `creatures` list of at least two different
   scenes.
8. At least one definition has `stat_block.attacks == []` and at least one has a
   non-empty `stat_block.attacks`.
9. At least two `hidden` entries exist across at least two scenes, each with a
   `dc` between 1 and 30 and a non-empty `discovered_by`.
10. At least one `exits` entry has a non-null `condition` and at least one has
    none. No `condition` string contains `==`, `!=`, `<` or `>`, nor — matched
    **case-insensitively and as whole words** — `true`, `false` or `flag`.
11. At least one `creatures` entry has `count` greater than 1.
12. `campaign.json` carries a `seed_character` with all of `name`, `race`,
    `character_class`, `background`, `appearance`, `abilities` (all six scores),
    `max_hp`, `armour_class` and a non-empty `inventory`.
13. At least one `consequences` entry, in any scene, contains the villain
    definition's `name` string verbatim. (That the entry actually makes the
    villain's escape a possible outcome — B12 — is the owner's judgement, and
    is part of criterion 23.)

### The command line

14. `app content validate`, run in the repository as checked out, exits **`0`**,
    writes `greenhollow/v1: ok` to stdout and **nothing** to stderr. **Stdout is
    compared after `.strip()`** — a trailing newline is not part of the
    contract; the line content is.

### The suite

15. A test that does **not** monkeypatch `CONTENT_ROOT` calls
    `service.list_campaign_ids()` and gets `["greenhollow"]`, and
    `service.list_versions("greenhollow")` and gets `["v1"]`.
16. A test that does **not** monkeypatch `CONTENT_ROOT` calls
    `service.load_campaign("greenhollow", "v1")` and it returns without raising.
17. That same test asserts, against the returned `LoadedCampaign`, the
    structural facts of criteria 7–11, plus `len(campaign.adventures) == 1` and
    `len(scenes) >= 3` — i.e. the brief is proven from the loaded objects. The
    `*.json` **file counts** of criteria 2 and 4 are not observable from a
    `LoadedCampaign` and stay filesystem assertions.
18. A test calls `service.load_scene("greenhollow", "v1", <the entry scene id,
    read from the loaded adventure>)` and gets that `Scene` back, and
    `service.load_definition("greenhollow", "v1", <a definition id from a
    placement>)` and gets that `Definition` back.
19. A test drives `content_app` with Typer's `CliRunner`, with no
    `CONTENT_ROOT` monkeypatch, and asserts exit code `0`, `result.stdout.strip()
    == "greenhollow/v1: ok"`, and empty stderr.
20. The whole backend suite passes: `make backend-test` is green, including
    every step-1.1 test, which continues to use `tmp_path` trees.

### The guide

21. **Closed in the previous pass, not re-measured** (§3). The criterion is:
    the authoring was done from `docs/modules/content.md` alone, and the
    author's report lists every field name, constraint, default or rule they
    had to guess at. It was met when this campaign was first authored. The
    P1-D20 pass performs no authoring, so there is nothing to measure; do not
    manufacture an authoring exercise to re-run it.
22. Every such guess is fixed **in `docs/modules/content.md`** (§7), not worked
    around in the content, and the guide still satisfies every criterion of
    step 1.2 §8. In a pure migration, expect nothing to fix.

### Human in the loop

23. **Closed in the previous pass, not re-measured** (§3). The owner has read
    the campaign prose and accepted it, including that B12's escape consequence
    reads as a possible outcome rather than a scripted one. The P1-D20 pass
    changes no prose, so that acceptance carries. **What replaces it for this
    pass is criterion 24**, which proves the prose really is unchanged.
24. **Migration fidelity.** Every scene object in the migrated adventure file
    is byte-identical, key for key and string for string, to the body of the
    `scenes/<id>.json` file it came from — provable against `git show` of the
    deleted files — and the scene order matches the order the deleted id list
    had. `campaign.json` and all three `definitions/*.json` show **no diff at
    all**. `git status` under `backend/content/` shows exactly one modified file
    and four deletions, and `backend/content/campaigns/greenhollow/v1/scenes/`
    no longer exists.

## 7. Recording a guide defect

If the guide was unclear, the fix goes in the guide:

- Report every guess in the agent report, explicitly, even where the guess
  turned out right — a correct guess is still an ambiguity.
- Edit `docs/modules/content.md` so the next author would not have to guess.
- **Do not** change `backend/app/modules/content/**`, and do not reshape the
  campaign to dodge an ambiguity rather than resolving it.
- If a guide defect turns out to be a phase-contract defect — a rule or a field
  the contract itself never pinned — **stop and report** instead of deciding it.

## 8. Static checks the dev agent runs

```bash
cp .env.dist .env                      # once, if not already done
docker compose run --rm --no-deps app-cli app content validate; echo "exit=$?"
```

Expected: exit `0`, stdout exactly `greenhollow/v1: ok`, stderr empty.

Also verify by hand, before handing over:

- Every file under `backend/content/` parses as JSON
  (`python -m json.tool < <file>`).
- `git status --porcelain -- backend/content/` shows **exactly one modified
  file and four deletions**, and nothing else; `docs/modules/content.md` appears
  only if §7 applied.
- `backend/content/campaigns/greenhollow/v1/scenes/` no longer exists.
- `git diff -- backend/content/` reads as a pure move: every `-` line for a
  scene reappears as a `+` line inside the adventure file, with no wording
  change. This is criterion 24 and it is checkable by eye.

**Do not run pytest** — the suite belongs to qa-backend. No ruff and no type
check apply: this step lands no Python. No Alembic round-trip: no migration.

## 9. The parallelisation split

This step is **not** parallel work — it is sequential inside itself, because the
evidence depends on the artefact.

| Agent | Owns | When |
|---|---|---|
| backend-dev | The migration of `backend/content/campaigns/greenhollow/v1/**` per §3 and §5, including the four deletions, and `docs/modules/content.md` under §7 only | First. Runs §8's checks |
| qa-backend | `backend/tests/content/**` — the unmocked tests of criteria 15–19, re-authored — and verification of criteria 1–14, 20, 22 and 24 | After the migration lands |

**This pass is dispatched normally, to both agents, with everything** —
`shared-knowledge.md`, this whole file including §6, and the amended guide. The
first pass's restricted reading list and its withholding of §6 existed to make
step-1.2's criterion 23 a real measurement of the guide; with no authoring to
measure, the restriction would now only hide the migration checklist from the
agent doing the migration. §3 states this and criteria 21 and 23 record it.

**The owner is not in the loop for this pass.** Criterion 23 is already closed;
criterion 24 is what an agent proves instead.

qa-backend's tests are written against the pinned ids `greenhollow` / `v1` and
derive everything else from the loaded objects, so they need no knowledge of the
story and can be re-authored before the migration lands.

## 10. Deviation clause

**Zero deviations from this spec and from
[`shared-knowledge.md`](shared-knowledge.md).** In particular: do not change the
schema, do not add a field, do not add a second adventure or version, do not
paste SRD text, and — the one that matters most in this pass — **do not change
one character of the campaign's prose, ids, numbers or ordering.** The move is
the whole of the work.
If a scene cannot be folded in as it stands, or the migrated tree will not
validate for a reason the guide does not explain, **stop and report it** — that
is a finding about the schema or the guide, and it is exactly what this step
exists to surface.
