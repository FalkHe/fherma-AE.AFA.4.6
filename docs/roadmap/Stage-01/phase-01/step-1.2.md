---
title: "Step 1.2 — The authoring guide and the documents this phase invalidates"
stage: 1
phase: 1
step: 1.2
status: spec
created: 2026-09-11
revised: 2026-09-11
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

In scope: the rewrite of one existing document, and — in the stage README —
**one amended row** in §9's doc-correction register. Everything else this step
once landed is already in place and is **verify-only, expect no diff**: the
`docs/README.md` index row, corrections C1–C3 and C5–C7, §9's
`general/architecture.md` row and §7's open-decision row. The only new
correction is C2a, plus one added clause in C4 (§6).

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
- `.env` exists, copied from `.env.dist`; `.env.dist` is owner-only and must
  not be edited. This step runs no command that reads either.
- **This step is a rework of landed documentation, not a first pass.** All of
  phase 1 landed in commits `e53e59b`, `61d6e7b` and `66efee6`;
  `shared-knowledge.md` was then amended by **P1-D20** (an adventure is one
  file, its scenes inline) and **P1-D21** (the term `Definition` stands), and
  the documents below still describe the pre-amendment shape.
- `docs/modules/content.md` **exists** and is the pre-amendment guide — the
  `scenes/` directory, eighteen rules, a five-file worked example. Rewrite the
  affected sections in place; do not start a new file and do not leave a
  paragraph describing the old layout anywhere in it.
- `docs/modules/` **exists** and contains only `content.md`.
- `docs/README.md`'s *Modules* section is **already a table with the
  `modules/content.md` row**, and "None yet" is already gone. §5 is therefore
  satisfied as it stands — verify it, change nothing.
- `docs/general/model.md`, `architecture.md` and `requirement-map.md` **already
  carry corrections C1–C7**. Only **C2a** is new, and C4 gains one clause; apply
  those two and leave the rest alone.
- `docs/roadmap/Stage-01/README.md` **already carries all three rows** of §7.
  Only the §7.1 `general/model.md` row's wording changes. See §7.
- `backend/app/modules/content/` exists and is being re-worked concurrently by
  step 1.1. **Do not read it and do not wait for it.** The guide is written from
  the phase contract, which is complete and amended.

## 3. Files this step creates or edits

All owned by **backend-dev**.

| File | Change |
|---|---|
| `docs/modules/content.md` | **Exists.** Rewrite it to the amended contract (§4). |
| `docs/README.md` | Already correct (§5). Verify only; expect no diff. |
| `docs/general/model.md` | C2a, and the added clause in C4 (§6). C1, C2, C3, C5 already landed. |
| `docs/general/architecture.md` | Already correct (C6). Verify only; expect no diff. |
| `docs/general/requirement-map.md` | Already correct (C7). Verify only; expect no diff. |
| `docs/roadmap/Stage-01/README.md` | One row amended in §9's register (§7). |

`docs/roadmap/Stage-01/README.md` is the **only** other plan document phase 1
edits. Add rows to the §9 and §7 tables — replacing one existing row, per §7.1 —
and change nothing else in that document.

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
   Include that content lives at `backend/content/`; that a campaign version is
   three kinds of file — `campaign.json`, `adventures/<id>.json` carrying the
   adventure **and its scenes**, and `definitions/<id>.json`; **why** the
   granularity is what it is (a scene belongs to one adventure, a definition is
   shared between adventures); that only `*.json` files are considered; and that
   a missing `adventures/` or `definitions/` directory is treated as empty.
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
   tags, so an author who sees `adventures/x.json: [R9] …` can look up what R9
   requires. State which rule is checked by the CLI rather than the loader (R3),
   and that a rule failing inside a scene names the **adventure** file and puts
   the scene id in the detail.
8. **The message grammar an author will see** —
   `<path>: [<TAG>] <detail>`, with `READ`, `SCHEMA` and `R2`…`R16` explained
   (R1 carries no tag of its own — it is reported as `[READ]` or `[SCHEMA]`),
   and the `app content validate` exit codes.
9. **The complete worked example** — phase contract §4.1, **reproduced
   verbatim**, all three files. This is the part an author copies from, so it
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
11. **What a `Definition` is**, in one sentence, in the template/instance terms
    of phase contract §3.4: a definition is the campaign-scoped template, and
    what appears in a scene during a run is an instance of it. This is what the
    directory name means and it is why `Scene.creatures` entries point at a
    `definition`.
12. **What the schema deliberately does not carry**, so an author does not try
    to add it: no items and no fixtures (creatures only); no level, no
    proficiency bonus, no skills, no player attacks — a monster's `to_hit` is
    the complete bonus and every other check resolves on the raw ability
    modifier; no portrait; no speed and no challenge rating.
13. **What one broken adventure does to the rest of the report**, in the terms
    of phase contract §11's drop block: an adventure that fails `[R6]`,
    `[READ]` or `[SCHEMA]` is dropped whole, so it produces no `[R7]`–`[R12]`
    findings, **and a definition only it referenced then shows up as `[R14]`
    unreferenced.** An author who fixes the adventure sees that `[R14]` go away
    on its own. The pre-amendment guide's troubleshooting paragraph around the
    old `[R8]` cluster describes rules that no longer exist and must be
    rewritten around this answer, not patched.
14. **A short authoring checklist** an author can run down before validating:
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
| C1 | `docs/general/model.md` | *Static files* | The content root is `backend/content/`, not `content/`. Give the reason in one clause: the Dockerfile copies `backend/` and compose bind-mounts it, so the path is identical in the image, under the dev bind mount and on the host, with no configuration. **In the same pass, strike "mounted read-only" from the *Content* bullet**: the landed mount is `./backend:/app`, read-write; content is read-only by convention — nothing writes it and the loader only reads — and is reviewed as diffs in PRs. |
| C2 | `docs/general/model.md` | *Static files* | `npcs/` and `monsters/` become one `definitions/` directory holding one `Definition` entity, which **always** carries a stat block. The same document already rules there is no npc/monster split; this is that ruling applied. |
| C2a | `docs/general/model.md` | *Static files* | **There is no `scenes/` directory.** The tree is `campaign.json`, `adventures/<id>.json` — the adventure **and its scenes** — and `definitions/<id>.json`. Give the reason in one clause: a scene belongs to exactly one adventure, a definition is campaign-scoped and shared between them. |
| C3 | `docs/general/model.md` | *Static files* | The scene-field line becomes the pinned set: `truth[]`, `npc_intent?`, `consequences[]`, `hidden[]`, `creatures[]`, `exits[]` — **a list, not a map** — and `pressure?`. |
| C4 | `docs/general/model.md` | *Static files* | `campaign.json` also carries the **seed player character**, and each adventure file carries a prose **`intro`**, an **`entry_scene`** and its **scenes inline**. |
| C5 | `docs/general/model.md` | *Content lives in git, runs pin a version* | State the mechanism: a version is a `v<n>` directory under the campaign, served whole by the loader, never edited in place. |
| C6 | `docs/general/architecture.md` | *System components* → **Adventure content** | Strike "Authored by an LLM once through a `generate_adventure` CLI that prompts with the SRD and enforces the schema". Content is **hand-authored**, validated by `app content validate`, and reviewed as a diff. Leave the rest of the bullet intact. |
| C7 | `docs/general/requirement-map.md` | *Task requirements*, row 3 | State the player-capability reading of stage README §8: every **player** capability has a surface; operator capabilities such as content validation are CLI-only by design, because putting developer machinery in the player UI is exactly what optional task Medium-8 penalises. One sentence in the row or immediately beneath the table — phase 11 makes the full argument. |

C1–C5 (including C2a) land in one edit of the *Static files* section; do not
fragment it.

## 7. The stage-register rows

**All three rows are already in `docs/roadmap/Stage-01/README.md` from the
previous pass. This step amends the wording of exactly one of them and adds
none.** §9 carries the phase-1 `general/model.md` row and the phase-8
`general/architecture.md` row; §7 carries the phase-8 open-decision row. Change
nothing else in that document — and in particular **do not add any row**, since
a second copy of either is precisely the defect criterion 20 fails on.

### 7.1 §9's two rows — one amended, one verified

Stage README §9 declares itself the single home for doc corrections. The
`general/model.md` phase-1 row is **already the enumerated one**; **amend it in
place** so that it also names the `scenes/` directory removed by P1-D20, giving
the wording below. The `general/architecture.md` row below is **already present
and already correct — verify it and change nothing.** Under no circumstances add
a second phase-1 `general/model.md` row: two rows for one contradiction set is
the duplication this register exists to prevent.

| Contradiction | File | Owning phase |
|---|---|---|
| The static-file tree's content root, its `scenes/` directory, the `npcs/` + `monsters/` split, the scene-field line, the missing `intro` / `entry_scene` / seed character, and the unstated version mechanism — enumerated in `roadmap/Stage-01/phase-01/shared-knowledge.md` §9.2 | `general/model.md` | 1 |
| The tool table's `get_monster(name)` row — with one `Definition` entity the binding is id- or name-addressed over `definitions`, and its final name and argument are phase 8's to pin | `general/architecture.md` | 8 |

### 7.2 §7's row — verified only

Phase contract §10.3 records an obligation that is a **note, not a control**: if
nothing carries it forward, phase 8 ships a leak that phase 9 discovers. §7 is
the register for exactly this — recorded, not settled, settled in the owning
phase's step spec. **This row is already present in §7's table from the previous
pass: verify it reads as below and change nothing. Do not add it again.**

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
7. The guide reproduces phase contract §11's rule table — **all sixteen rules,
   carrying fifteen `[R<n>]` tags**, because R1 has no tag of its own and is
   reported as `[READ]` or `[SCHEMA]`. The tags present are `[R2]` and
   `[R3]`…`[R16]`. The guide marks R3 as the CLI-level check, and the strings
   `[R17]` and `[R18]` appear nowhere in it.
8. The guide reproduces the worked example of phase contract §4.1 in full — all
   three files — and every JSON block in it is parseable JSON.
9. The guide states the message grammar `<path>: [<TAG>] <detail>`, explains
   `READ`, `SCHEMA` and `R<n>` (and that R1 carries no tag of its own), and
    gives the `app content validate` exit codes
   `0` and `1` with their conditions.
10. The guide contains, under its own heading, the sentence **"A scene is facts,
    intentions and consequences, never a script."** and the sentence **"An exit
    condition is prose the agent judges, never a flag, a variable or a
    comparison."**
11. The guide states, in one sentence, that a `Definition` is the
    campaign-scoped template and that what appears in a scene during a run is an
    instance of it.
12. The guide states that an adventure file carries its scenes inline, that
    there is no `scenes/` directory, and why.
13. The guide states that content declares no items and no fixtures, and that
    there is no level, proficiency bonus, skill list or authored player attack.
14. The guide contains an authoring checklist covering: reachability from
    `entry_scene`, at least one scene with no exits, every definition referenced,
    no duplicate placement in a scene, unique definition names.
15. `docs/general/model.md`'s *Static files* section shows the content root as
    `backend/content/`, shows a single `definitions/` directory, shows **no
    `scenes/` directory** and no `npcs/` or `monsters/` directory, and shows the
    scene-field set of C3 as the content of an adventure file.
16. `docs/general/model.md` states that `campaign.json` carries the seed player
    character and that an adventure carries `intro` and `entry_scene`.
17. `docs/general/model.md`'s *Content lives in git, runs pin a version* section
    states the `v<n>` directory mechanism.
18. `docs/general/architecture.md` no longer contains the string
    `generate_adventure`, and its *Adventure content* bullet says the content is
    hand-authored and validated by `app content validate`.
19. `docs/general/requirement-map.md`'s requirement-3 entry states the
    player-capability reading and names content validation as an operator
    capability.
20. `docs/roadmap/Stage-01/README.md` §9's table carries the enumerated
    `general/model.md` row of §7.1 in its **amended** wording — the one that
    also names the `scenes/` directory — and carries no second phase-1
    `general/model.md` row. §7.1's `general/architecture.md` row and §7.2's
    open-decision row are **already present from the previous pass and are
    unchanged**, so `git diff -- docs/roadmap/Stage-01/README.md` shows
    **exactly one changed row and nothing else**. A diff showing those two rows
    added again is a defect: they would then be duplicated.
21. `docs/general/glossary.md` is unchanged.
22. No file under `backend/` appears among the files this step's agent edited,
    as listed in its own report, and no `docs/` file outside §3's table was
    touched. **`backend/` paths in the working tree are not evidence**: step 1.1
    runs concurrently in the same tree and legitimately produces them.
23. **The falsifiable criterion — closed in the previous pass, not re-measured
    in the P1-D20 rework.** The criterion is: step 1.3's author works from
    `docs/modules/content.md` alone, without opening
    `backend/app/modules/content/`, and the campaign they produce passes
    `app content validate` on the first run after the owner's prose review; any
    field name, constraint or rule the author had to guess at is a defect in
    this guide and is fixed in the guide, not worked around in the content.
    **It was measured and passed against the *pre-amendment* guide**, and that
    is the limit of what carries: the sections this pass rewrites — the
    three-file layout, the three-file worked example, R1–R16 and the `[R14]`
    drop paragraph — are exactly what a fresh author would trip on and they
    carry **no independent measurement of their own**. Step 1.3 is now a
    mechanical migration of already-accepted prose (step-1.3 §3), so there is no
    authoring in this pass to measure against, and criteria 1–22 are the
    mechanical substitute. This criterion stands, unmeasured, for the next
    campaign authored from this guide.

Criterion 23 was verified in step 1.3's first pass and is the reason this step
exists; it is carried, not re-measured (see the criterion).

## 9. Static checks the dev agent runs

This step lands no code, so there is nothing to lint, type-check or boot. The
checks are:

```bash
git status --porcelain -- docs/   # the docs/ paths this step touched
```

- **It should list exactly three paths**: `docs/modules/content.md`,
  `docs/general/model.md` and `docs/roadmap/Stage-01/README.md`. The other
  entries of §3's table are verify-only in this pass and a diff on any of them —
  `docs/README.md`, `docs/general/architecture.md`,
  `docs/general/requirement-map.md` — means something was re-applied that was
  already landed. **Do not run a tree-wide `git diff --stat`**: step 1.1 runs
  concurrently in the same working tree, so `backend/` paths are expected there
  and are out of scope for this step.
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
| backend-dev | The rewrite of `docs/modules/content.md`, correction C2a and C4's added clause in `docs/general/model.md`, and the one amended §9 row in `docs/roadmap/Stage-01/README.md` (§7). Everything else named in §3 is verify-only. Nothing else. |
| qa-backend | Verification of criteria 1–22 against the landed documents. Criterion 23 is carried from the previous pass and is not re-measured. |

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
