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

Author the campaign the game ships with — one campaign, one adventure, at least
three scenes, its definitions and a seed player character — **from
`docs/modules/content.md` alone**, and prove the shipped tree loads and
validates.

**This step is dispatched in two halves, with different reading lists (§9).**

- The **authoring half** reads `docs/modules/content.md` and `step-1.3.md`
  §1–§5 and §7–§8 — §6 is withheld, because it names the field set the guide is
  supposed to supply (§9) — and nothing else. It does **not** read
  `shared-knowledge.md` and does **not** read `backend/app/modules/content/`.
  Everything it needs that the guide does not carry is in §4 of this file.
- The **QA half** reads `step-1.3.md` and
  [`shared-knowledge.md`](shared-knowledge.md), the binding phase contract, and
  may read anything.

§3 explains why the split is structural rather than a request.

**Human in the loop.** The owner has chosen the subject (§4). The owner reads
the finished prose and accepts or rejects it before the step is done. No agent
judges prose quality, and nothing in the system validates it.

**Depends on steps 1.1 and 1.2.** Both must have landed.

## 1. Scope

In scope:

- `backend/content/campaigns/greenhollow/v1/**` — the authored tree.
- `backend/tests/content/**` — qa-backend's unmocked shipped-tree tests.
- `docs/modules/content.md` — **only** to fix a defect the authoring exposed
  (§7).

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

## 2. Environment you will meet

- The Docker stack is **down**.
- **`.env` exists**, copied from `.env.dist`; `.env.dist` stays owner-only and
  must not be edited. It has to exist: without it `app content validate` raises
  a `ValidationError` before doing any work, and `docker compose run app-cli`
  cannot start at all. If it is missing, run `cp .env.dist .env`.
- Alembic head is `0001`. **This step adds no migration.**
- `backend/app/modules/content/` exists and `app content validate` works
  (step 1.1).
- `docs/modules/content.md` exists (step 1.2).
- `backend/content/` **does not exist.** Running `app content validate` right
  now exits `1` with `no campaigns found under /app/content`. That is the
  starting state, and making it exit `0` is this step's headline evidence.

## 3. The rule that makes this step meaningful

**The authoring agent is dispatched with `docs/modules/content.md` and
`step-1.3.md` §1–§5 and §7–§8 only.** The restriction is enforced by the
dispatch, not requested of the agent — an agent that has already read
`shared-knowledge.md` has seen the complete schema, the worked example and the
rule table, and criterion 21 would then measure that agent's self-restraint
rather than the guide's completeness.

Step 1.2's guide claims an agent can author a conformant campaign from it alone.
This step is the only test of that claim, and it is criterion 21 — the reason
step 1.2 exists at all. Reading `backend/app/modules/content/schemas.py`,
`service.py` or `shared-knowledge.md` during authoring silently destroys the
evidence.

If the guide is unclear, incomplete or wrong about a field name, a constraint, a
default or a rule — **write down what you had to guess**, finish the campaign,
and fix the guide (§7). A guess you had to make is a defect in the guide, not a
licence to consult the code.

## 4. The authoring brief

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
| B3 | **At least three scenes**, all belonging to that one adventure |
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

| File | Owner | Contents |
|---|---|---|
| `backend/content/campaigns/greenhollow/v1/campaign.json` | backend-dev | Campaign metadata, the ordered adventure list, the seed player character |
| `backend/content/campaigns/greenhollow/v1/adventures/<id>.json` | backend-dev | The one adventure: title, `intro`, `entry_scene`, its scene ids |
| `backend/content/campaigns/greenhollow/v1/scenes/<id>.json` | backend-dev | Three or more scenes |
| `backend/content/campaigns/greenhollow/v1/definitions/<id>.json` | backend-dev | The patron, the goblin boss, and whatever else the scenes place |
| `docs/modules/content.md` | backend-dev | **Only** if the authoring exposed a guide defect (§7) |
| `backend/tests/content/**` | qa-backend | The unmocked shipped-tree tests (§6, criteria 15–19) |

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
3. `scenes/` contains at least three `*.json` files, and every one of them is
   listed in that adventure's `scenes`.
4. Exactly the scenes listed in the adventure exist — no orphan file, no missing
   file.
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
    `*.json` **file counts** of criteria 2–4 are not observable from a
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

21. The authoring was done from `docs/modules/content.md` alone, and the author's
    report lists every field name, constraint, default or rule they had to guess
    at — the empty list being the strongest possible result.
22. Every such guess is fixed **in `docs/modules/content.md`** (§7), not worked
    around in the content, and the guide still satisfies every criterion of
    step 1.2 §8.

### Human in the loop

23. The owner has read the campaign prose and accepted it — including that
    B12's escape consequence is present and reads as a possible outcome rather
    than a scripted one. **This criterion is closed by the owner, not by an
    agent**, and the step is not done until it is.

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

- Every authored file parses as JSON (`python -m json.tool < <file>`).
- `git diff --stat` shows only `backend/content/` paths, plus
  `docs/modules/content.md` if §7 applied.

**Do not run pytest** — the suite belongs to qa-backend. No ruff and no type
check apply: this step lands no Python. No Alembic round-trip: no migration.

## 9. The parallelisation split

This step is **not** parallel work — it is sequential inside itself, because the
evidence depends on the artefact.

| Agent | Owns | When |
|---|---|---|
| backend-dev (authoring half) | `backend/content/campaigns/greenhollow/v1/**`, and `docs/modules/content.md` under §7 only | First. Authors from the guide; runs §8's checks |
| owner | Criterion 23 | After authoring, before QA is dispatched |
| qa-backend | `backend/tests/content/**` — the unmocked tests of criteria 15–19 — and verification of criteria 1–14 and 20–22 | After the owner accepts |

**The authoring half is dispatched with exactly two documents:
`docs/modules/content.md`, and `step-1.3.md` cut down to §1–§5 and §7–§8.** Not
`shared-knowledge.md`, not `steps.md`, not `step-1.1.md`, not `step-1.2.md`, and
no file under `backend/app/modules/content/`. **§6 is withheld** because it
enumerates roughly a dozen field names the guide is supposed to supply —
`character_class`, `armour_class`, `stat_block.attacks`, the nine
`seed_character` fields, `hidden` / `dc` / `discovered_by`, `creatures` /
`count`, `exits` / `condition`, `consequences`, `entry_scene` — and is the QA
half's checklist, not the author's; §8 already carries the exit-0 check the
author needs. This is a property of the briefing, not an instruction the agent
is trusted to honour, and it is what makes criterion 21 a measurement rather
than a request.

The QA half is dispatched normally, with `shared-knowledge.md` and everything
else. qa-backend authoring its tests before the content exists is fine and
encouraged: criteria 15–19 are written against the pinned ids `greenhollow` /
`v1` and derive everything else from the loaded objects, so they need no
knowledge of the story.

## 10. Deviation clause

**Zero deviations from this spec** — and, for the QA half, from
[`shared-knowledge.md`](shared-knowledge.md). In particular: do not change the
schema, do not add a field, do not add a second adventure or version, do not
read `backend/app/modules/content/` or `shared-knowledge.md` while authoring,
and do not paste SRD text.
If the brief of §4 cannot be satisfied within the pinned schema, **stop and
report it** — that is a finding about the schema, and it is exactly what this
step exists to surface.
