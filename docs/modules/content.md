# Adventure content — the authoring guide

This is the complete reference for authoring a campaign. It is written so that
an author with **no access to the schema code** can produce a campaign tree
that `app content validate` accepts on the first run: every field, every
constraint that rejects a file, and every referential rule is stated here, not
merely implied.

## 1. What you are authoring, and what it is not

Two different things live in these files and this guide never confuses them:

- the **Campaign-Definition** and the **Adventure-Definitions** — the authored
  JSON *structures*: ids, lists, object templates, placements, exits.
  Machine-read, validated, referenced by id.
- the **Story** (**Prose**) they carry — `truth`, `npc_intent`, `consequences`,
  descriptions, intros. Read by the Dungeon Master and retold to the player;
  validated only for being non-empty.

Both are **hand-authored, version-pinned, static JSON checked into git**,
read-only at runtime. A run references a campaign by its id and a pinned
version and never sees any other version, even after the campaign is extended.
They are **not** a database, **not** a script that decides what the player
does, and **not** generated at runtime — there is no generation CLI in this
stage; this document is the only authoring aid.

## 2. Directory layout

```
backend/content/
└── campaigns/
    └── <campaign_id>/
        └── <version>/
            ├── campaign.json                   # metadata + seed_character + object_templates[]
            └── adventures/<adventure_id>.json  # the adventure and its scenes, inline
```

Example: `backend/content/campaigns/hollow-reach/v1/campaign.json`.

A campaign version is exactly **two kinds of file**:

- `campaign.json` — the campaign's metadata, its seed player character, and
  every `object_templates[]` entry the campaign declares.
- `adventures/<adventure_id>.json` — **the whole adventure, its scenes
  included, inline.** There is no `scenes/` directory and no separate scene
  file.

**Why the granularity is what it is.** A scene belongs to exactly one
adventure and cannot be shared or orphaned, so it lives inside that
adventure's file. An object template is campaign-scoped — the villain of
adventure 1 can return in adventure 3, and an item found in one adventure can
be carried into another — so it cannot live inside any one adventure and
stays in the campaign-scoped file. There is no `definitions/` directory: a
template has no filename of its own, only an `id` field.

- **Only `*.json` files are considered.** A `README.md`, a `.DS_Store` or an
  editor swap file sitting inside `adventures/` is ignored entirely — never
  read, never reported as an orphan.
- **A missing `adventures/` directory is treated as an empty directory**, not
  an error by itself — but an adventure that `campaign.json` expects and does
  not find still fails the referential rules below (§7).

## 3. Versioning

A version is a directory literally named `v<n>` — `v1`, `v2`, and so on — a
digit sequence with no leading `v` missing and no decimal point. A version is
never edited in place once it exists: a campaign is extended by **copying the
whole tree to `v2` and editing there**, so a run pinned to `v1` stays
reproducible forever. There is no manifest, no semantic version and no
`published` flag — the directory name is the only version record there is.

## 4. Casing and naming rules

These are the mistakes an author (or a generator) makes by default. Each is a
rule, not a suggestion:

- **JSON keys are `snake_case`** and identical, letter for letter, to the field
  names in this document. There is no camelCase anywhere in these files.
- **Every id is lowercase kebab-case**: `^[a-z0-9]+(-[a-z0-9]+)*$` — lowercase
  letters, digits and single hyphens between segments. `Bog-Lurker`, `bog_lurker`
  and `bog--lurker` are all rejected.
- **The player-class field's JSON key is `character_class`, not `class`.**
  `class` is a Python reserved word; the schema never uses it.
- **The armour-class field's JSON key is `armour_class`, not `armor_class`.**
  The project's glossary pins the British spelling and every authored file uses
  it exactly.

## 5. Every model and every field

Every model below forbids unknown keys (§6) — do not add a field that is not
listed here.

### 5.1 `Abilities`

The six 5e ability scores. Every field is **required**; a partial set is not
meaningful.

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `strength` | integer, 1–30 | yes | — | Raw ability score |
| `dexterity` | integer, 1–30 | yes | — | Raw ability score |
| `constitution` | integer, 1–30 | yes | — | Raw ability score |
| `intelligence` | integer, 1–30 | yes | — | Raw ability score |
| `wisdom` | integer, 1–30 | yes | — | Raw ability score |
| `charisma` | integer, 1–30 | yes | — | Raw ability score |

### 5.2 `Attack`

One attack a stat block, or an item, can make.

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `name` | prose string | yes | — | The attack's name, shown to the player |
| `to_hit` | integer | yes | — | The **complete** bonus added to the d20 — already includes any proficiency the author intends; nothing is added on top |
| `damage` | prose string | yes | — | A dice expression, e.g. `"1d6+2"`, passed verbatim to the dice roller — not validated by content loading |

### 5.3 `StatBlock`

Carried by every `CreatureTemplate` and by the `SeedCharacter`'s inline fields
(§5.11). It is what makes an entity able to exist as a mechanical creature.

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `max_hp` | integer, ≥1 | yes | — | Maximum (and starting) hit points |
| `armour_class` | integer, ≥1 | yes | — | Armour class |
| `abilities` | `Abilities` | yes | — | The six ability scores |
| `attacks` | list of `Attack` | no | `[]` | Attacks this creature can make |
| `traits` | list of prose strings | no | `[]` | Special abilities, in prose, for the DM's narration |

**`attacks: []` is what "cannot fight" means.** A harmless NPC — an innkeeper,
a merchant — still has hit points and an armour class, and simply has an empty
`attacks` list. There is no separate "non-combatant" shape.

Deliberately absent (§9): speed, challenge rating, level, proficiency bonus,
skills, saves.

### 5.4 `ObjectTemplate` — a `kind`-discriminated union

The campaign-scoped blueprint of one thing a scene can contain: a creature, an
item or a fixture. Each placement of it becomes one object during a run. One
shared head, three tails.

**The shared head — every kind carries these:**

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `id` | content id | yes | — | How a placement, a carry and a `bypassed_by` entry name it. Unique within the campaign (R13) |
| `kind` | `"creature"` \| `"item"` \| `"fixture"` | yes | — | The discriminator |
| `name` | prose string | yes | — | Player-facing; unique within the campaign, case-insensitively, across all three kinds (R15) |
| `description` | prose string | yes | — | What it is and what it looks like; DM-prompt material |

**`CreatureTemplate`** — one entity used for both NPCs and monsters; there is
no npc/monster split.

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `disposition` | prose string | yes | — | What it wants and how it treats the player |
| `stat_block` | `StatBlock` | yes | — | Required on every creature — `attacks: []` is what "cannot fight" means |

**`ItemTemplate`**

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `attacks` | list of `Attack` | no | `[]` | What the item offers whoever wields it; `[]` is an ordinary object with no combat use |

**`FixtureTemplate`**

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `checks` | list of `FixtureCheck`, min length 1 | yes | — | Every authored way to act on the fixture, each with the DC the DM must not invent |

A fixture with no checks is scenery, and scenery belongs in `truth` rather than
being declared — that is what separates the two. An item may legitimately have
no attacks, so its list defaults to empty; a fixture may not legitimately have
no checks, so its list has no default at all.

**Rejecting a wrong-kind field is the point.** An `ItemTemplate` carrying
`stat_block`, a `CreatureTemplate` carrying `checks` and a `FixtureTemplate`
carrying `attacks` are all loud `[SCHEMA]` failures, and a template with an
unknown or missing `kind` fails on the discriminator.

### 5.5 `FixtureCheck`

One entry of a `FixtureTemplate.checks` list.

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `action` | prose string | yes | — | What a character *does*, in plain prose — not a skill enum |
| `dc` | integer, 1–30 | yes | — | The authored target number |
| `success` | prose string | yes | — | What is true afterwards — a fact, never narration to be recited |
| `bypassed_by` | list of content ids | no | `[]` | The ids of the **item**-kind templates that make this check succeed with no roll. Holding any one of them is enough. `[]` means nothing bypasses it |

`bypassed_by` is the key-for-the-lock and the blade-for-the-rope: each entry
names a template, never an instance and never a condition. **It is a list, and
`[]` is the only way to say "nothing bypasses this."** It is **disjunctive** —
an *any-of*, never an all-of — and **explicit**: the eligible items are
enumerated by the author, never inferred by the DM from an item's description
or name. There is no bare-string form and no `null`: an absent key, an
explicit `[]` and "no shortcut" are one value and one representation.

### 5.6 `Secret`

One entry of a scene's `hidden` list — a fact the DM knows and the player must
earn.

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `fact` | prose string | yes | — | What is true but not apparent |
| `dc` | integer, 1–30 | yes | — | The target number to discover it |
| `discovered_by` | prose string | yes | — | Prose describing the ability/skill and the action that reveals it, e.g. `"a Wisdom (Perception) check on entering, or searching the crates"` — not a skill enum |

`hidden` and `dc` are DM-only and must never be shown to the player.

### 5.7 `Placement` and `Carried`

One entry of a scene's `placements` list, and one entry of a placement's
`carries` list.

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `Placement.template` | content id | yes | — | The `ObjectTemplate` id this placement instantiates |
| `Placement.count` | integer, ≥1 | no | `1` | How many instances this placement creates |
| `Placement.carries` | list of `Carried` | no | `[]` | What **each** instance this placement creates owns from the start |
| `Carried.template` | content id | yes | — | An **item**-kind template id |
| `Carried.count` | integer, ≥1 | no | `1` | How many of it each owning instance holds |

**`carries` is per created instance, not per placement.**
`{"template": "goblin", "count": 3, "carries": [{"template": "sling"}]}` is
three goblins with one sling each — three goblins sharing one sling is not
expressible, and does not need to be.

**Who may carry.** A `creature` placement and a `fixture` placement may both
carry — a boss holding a key and a sack holding fleeces are the same
mechanic. **A placement whose template kind is `item` has empty `carries`**
(R18) — an item does not itself carry anything.

**One level deep, never recursive.** A `Carried` entry has no `carries` of its
own; carrying does not nest.

**A template may appear at most once in a scene's `placements` list, and at
most once in any single placement's `carries` list** (R16) — write
`{"template": "goblin", "count": 3}` for three goblins, never three separate
entries.

### 5.8 `Exit`

One entry of a scene's `exits` list — **a list, not a map**.

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `id` | content id | yes | — | Which exit `use_exit(actor, exit)` addresses. Unique within its **own scene only** (R19) — unlike scene and template ids, an exit id may repeat in another scene |
| `kind` | `"scene"` \| `"adventure_end"` | no | `"scene"` | A `scene` exit moves the run to another scene; an `adventure_end` exit ends the adventure there |
| `to` | content id or `null` | see purpose | — | The id of a scene in the **same adventure**. Required on a `scene` exit; an `adventure_end` exit must not carry it |
| `description` | prose string | yes | — | What the player perceives as the way on |
| `condition` | prose string or `null` | no | `null` | Prose the DM judges before allowing the exit; `null` means always open |

**Why an exit needs its own id.** Changing scene and ending the adventure are
one mechanic, `use_exit(actor, exit)` — the DM addresses an exit by id, never
by its position in the list. An adventure ends by the player taking a
particular exit, not by wandering into a scene that happens to have none: some
scene reachable from `entry_scene` must carry an `adventure_end` exit (R10).
There is no more "terminal scene" shape — a scene with `exits: []` is simply a
scene with no way on, not how an adventure ends.

### 5.9 `Scene`

**A scene is not a file.** It is an element of its adventure's `scenes` list
(§5.10), so a scene belongs to exactly one adventure and cannot be orphaned or
shared between adventures. It keeps its own `id`, which is how exits, runs and
the loaded campaign's flat scene map address it. Facts, intentions and
consequences — never a script (see §10).

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `id` | content id | yes | — | Unique across the **whole campaign** (R8), not just the adventure |
| `title` | prose string | yes | — | Short location label, shown to the player |
| `truth` | list of prose strings, min length 1 | yes | — | What is true here — at least one fact is required |
| `npc_intent` | prose string or `null` | no | `null` | What the creatures present want; `null` when the scene has no creature placements |
| `consequences` | list of prose strings | no | `[]` | What follows from plausible player action — never what the player does |
| `hidden` | list of `Secret` | no | `[]` | DM-only secrets |
| `placements` | list of `Placement` | no | `[]` | What is here: creatures, items and fixtures alike |
| `exits` | list of `Exit` | no | `[]` | Ways out of the scene. Ending the adventure happens through an `adventure_end` exit (§5.8), not through an empty list |
| `pressure` | prose string or `null` | no | `null` | What forces the scene forward |

### 5.10 `Adventure`

File: `adventures/<id>.json` — **the whole adventure, its scenes included.**

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `id` | content id | yes | — | Must equal the filename stem |
| `title` | prose string | yes | — | Player-facing title |
| `intro` | prose string | yes | — | Prose read aloud when the adventure starts |
| `entry_scene` | content id | yes | — | Must be the id of one of this adventure's own `scenes` |
| `scenes` | list of `Scene`, min length 1 | yes | — | The scenes themselves, inline — not ids. Order is authoring convenience only; traversal is defined by exits and `entry_scene` |

### 5.11 `SeedCharacter`

The starting player character, carried inline in `campaign.json`. It is a
**fixture** so a run has a character before the (later) character-generation
agent exists — it is not a player-facing option.

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `name` | prose string | yes | — | Character name |
| `race` | prose string | yes | — | Character race |
| `character_class` | prose string | yes | — | Character class — the JSON key is `character_class`, never `class` |
| `background` | prose string | yes | — | One or two sentences of backstory |
| `appearance` | prose string | yes | — | DM narration material |
| `abilities` | `Abilities` | yes | — | The six ability scores |
| `max_hp` | integer, ≥1 | yes | — | Starting/maximum hit points |
| `armour_class` | integer, ≥1 | yes | — | Armour class |
| `inventory` | list of content ids | no | `[]` | Starting items — each id must name a declared **item**-kind template (R20), never free text |

No `portrait` field, no `level`, no proficiency, no authored attacks — see §9.
`inventory` is the seed character's only reference into the
Campaign-Definition: a starting pack has to name real item templates so that
later mechanics — combat, carrying, giving an item away — can act on a real
weapon or tool instead of a sentence. R14 counts each entry as a use of the
template it names, and R20 rejects an entry that names no template, or names
one that is not an `item`.

### 5.12 `Campaign`

File: `campaign.json`.

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `id` | content id | yes | — | Must equal the campaign's directory name |
| `title` | prose string | yes | — | Player-facing title |
| `summary` | prose string | yes | — | The pitch, shown when a run starts |
| `adventures` | list of content ids, min length 1 | yes | — | **Ordered** — the play order |
| `seed_character` | `SeedCharacter` | yes | — | The starting player character |
| `object_templates` | list of `ObjectTemplate`, min length 1 | yes | — | Every creature, item and fixture template the campaign declares |

`object_templates` is a **list**, not a map — the id is already on each
element. Its order is authoring convenience and carries no meaning.

There is no `version` field: the version is the directory name and nothing
else, so the two can never disagree.

## 6. Every constraint that actually rejects a file

- **Unknown keys are rejected, not ignored.** Every model forbids extra
  properties; a typo in a key name is a loud load error.
- **Every id must match `^[a-z0-9]+(-[a-z0-9]+)*$`.**
- **Every prose string is stripped of surrounding whitespace and must then be
  non-empty.** `"   "` is rejected — it strips to the empty string.
- **Numeric bounds**: every ability score is 1–30; every `dc` is 1–30; `max_hp`
  and `armour_class` are ≥1; `Placement.count` and `Carried.count` are ≥1.
- **List minimums**: `Scene.truth` needs at least one entry; `Adventure.scenes`,
  `Campaign.adventures` and `Campaign.object_templates` need at least one
  entry each; `FixtureTemplate.checks` needs at least one entry.
- **`bypassed_by` is a list, and only a list.** A bare string, `null`, or an
  entry that is not a valid content id are all rejected.
- **Carrying does not nest.** A `Carried` entry carrying a `carries` key of
  its own is rejected.
- **A `scene`-kind exit requires `to`; an `adventure_end`-kind exit must not
  carry `to`.** Either mismatch is a `[SCHEMA]` failure on the exit itself.
- No string and no list has an upper bound — nothing here rejects a file for
  being long.

## 7. The referential rule list

Applied after every file in the tree has already passed the field checks
above. Each rule's tag is what appears in a validation error, in the form
`<path>: [<TAG>] <detail>` (§8) — an author who sees `[R11]` can look the
number up here. **Twenty rules, `R1` through `R20`; `R1` and `R3` carry no
tag of their own in `errors[]`.**

| # | Where checked | Rule |
|---|---|---|
| R1 | loader | `campaign.json` exists, is readable and passes its field checks. Reported as `[READ]` or `[SCHEMA]`, never `[R1]` |
| R2 | loader | `campaign.id` equals the campaign's directory name |
| R3 | **CLI, not the loader** | The version directory name matches `^v[0-9]+$` |
| R4 | loader | Every id in `campaign.adventures` has a matching `adventures/<id>.json`, with no duplicate ids in the list |
| R5 | loader | Every `*.json` file in `adventures/` is listed in `campaign.adventures` — no orphans |
| R6 | loader | Each adventure's `id` equals its own filename stem |
| R7 | loader | `adventure.entry_scene` is the `id` of one of that adventure's own `scenes` |
| R8 | loader | A scene `id` appears **at most once across the whole campaign** — twice in one adventure and once each in two adventures are the same failure |
| R9 | loader | Every `scene`-kind exit's `to` names a scene in the **same** adventure, and is never the scene's own id |
| R10 | loader | Some scene reachable from the entry scene carries an `adventure_end` exit |
| R11 | loader | Every scene of an adventure is reachable from `entry_scene` by following exits (conditions ignored for this check); the entry scene itself counts as reached; an exit without `to` (an `adventure_end` exit) is not followed further |
| R12 | loader | Every object-template reference resolves to a declared template — `placements[].template`, `carries[].template` and every entry of every `checks[].bypassed_by` list alike |
| R13 | loader | An object template `id` appears at most once in `campaign.object_templates`; the first occurrence keeps the id, every later one is excluded from the loaded campaign |
| R14 | loader | Every declared object template is referenced at least once — by a placement, a carry, an entry of any `bypassed_by` list, or an entry of `seed_character.inventory` |
| R15 | loader | An object template `name` is unique across the campaign, compared case-insensitively after stripping, **across all three kinds** |
| R16 | loader | A template appears at most once in a scene's `placements` list, and at most once in any single placement's `carries` list |
| R17 | loader | Every `carries[].template` and every entry of every `checks[].bypassed_by` list resolves to a template whose `kind` is `item` |
| R18 | loader | A placement whose template `kind` is `item` has `carries == []` |
| R19 | loader | An exit `id` appears at most once within its own scene's `exits` list |
| R20 | loader | Every `seed_character.inventory` entry resolves to a declared template whose `kind` is `item` |

**Ordering between R12 and R17.** R17 is evaluated only for a reference R12
already resolved — an unknown id yields `[R12]` and nothing else, so one
mistake never produces two findings. This is judged per reference: in a
`bypassed_by` list holding an unknown id, an item and a creature, the unknown
one yields `[R12]`, the creature yields `[R17]`, and the item yields nothing.

**R20 is R12 and R17 folded into one tag.** A `seed_character.inventory`
entry has only one rule to fail: an unresolvable id and an id resolving to a
non-`item` template are both reported `[R20]`, unlike a placement or a carry
reference where the two shapes of failure are two different tags.

**What an id/filename mismatch gets you.** An adventure is always identified
by its **filename**, never by the `id` field inside the file:

- An **adventure** whose `id` disagrees with its filename (`[R6]`) is dropped:
  it produces no other findings about itself, and its scenes are reported by
  nothing — they are not files and cannot be orphans.
- A **scene** has no filename, so its identity is its `id` field; `R8` is
  what keeps that identity unambiguous across the whole campaign.
- An **object template** has no filename either, so its identity is its `id`
  field; `R13` is what keeps that identity unambiguous.

**What one broken adventure does to the rest of the report.** An adventure
that fails `[R6]`, `[READ]` or `[SCHEMA]` is dropped whole: it is excluded from
every later rule and produces no further findings about itself, and its scenes
go with it. **A dropped adventure contributes no references to R14**, so a
template that only that adventure referenced is reported `[R14]` as
unreferenced — this is the deliberate answer, not an oversight.

`seed_character` has no referential rule — it references nothing else in the
Campaign-Definition.

## 8. The message grammar and exit codes

Every reported problem has the shape:

```
<path relative to the version directory>: [<TAG>] <detail>
```

- `[READ]` — the file could not be read, or is not valid JSON.
- `[SCHEMA]` — the file parsed as JSON but failed a field check (§6).
- `[R2]` … `[R20]` — the numbered referential rule that failed (§7). **R1 has
  no tag of its own** — its failure is always reported as `[READ]` or
  `[SCHEMA]` against `campaign.json`. **R3 never appears here** — it is a
  CLI-level check, not a loader rule.

**Every rule about a template names `campaign.json`**, and puts the template
id in the detail. **Every rule about a placement, a carry or an exit names
the adventure file**, and puts the scene id in the detail. **R20 names
`campaign.json`**, and puts the offending inventory entry in the detail —
there is no scene or adventure file to name.

Example messages:

```
adventures/goblins-of-greenhollow.json: [R9] scene 'lair-maw': exit targets unknown scene 'under-whee'
adventures/goblins-of-greenhollow.json: [R12] scene 'lair-hollow': unknown object template 'notched-cleavor'
adventures/goblins-of-greenhollow.json: [R17] scene 'lair-hollow': carried template 'goblin' is not an item
adventures/goblins-of-greenhollow.json: [R18] scene 'village-green': item placement 'bent-horseshoe' cannot carry
adventures/goblins-of-greenhollow.json: [R19] scene 'lair-hollow': duplicate exit id 'leave-the-hollow'
campaign.json: [R12] fixture 'thorn-screen': check 1 bypassed_by entry 0 names unknown object template 'shepherds-knifr'
campaign.json: [R13] duplicate object template id 'goblin'
campaign.json: [R14] object template 'stolen-fleece' is not referenced by any scene
campaign.json: [R15] object template 'zzz-key' duplicates the name 'Rusty Key'
campaign.json: [R17] fixture 'thorn-screen': check 1 bypassed_by entry 0 'goblin' is not an item
campaign.json: [R20] seed character inventory names unknown object template 'shepherds-knifr'
campaign.json: [SCHEMA] object_templates.0.creature.stat_block.max_hp: Input should be a valid integer
```

Running `app content validate` checks every campaign and every version found
under the content root:

| Exit code | Condition |
|---|---|
| `0` | At least one campaign version was found, every one is valid, no non-conformant version directory exists, and every campaign has at least one conformant version |
| `1` | Any campaign version failed validation, any version directory name is non-conformant (`[R3]`), any campaign has no conformant version directory, or no campaign was found at all |

## 9. What the schema deliberately does not carry

Do not try to add these — they have no field:

- **No hit points and no armour class on an item or a fixture.** A fixture's
  resistance is authored as a `checks[].dc`, never HP/AC.
- **No weight, no value, no stack size, no slot** on any object template.
- **No `consumable`, `quantity` or durability on `ItemTemplate`.** Quantity
  lives on the placement (`count`).
- **No `locked` / `open` state on `FixtureTemplate`.** A template is
  immutable; state belongs to the instance, not the authored file.
- **No level, no proficiency bonus, no skill list, no authored player
  attacks.** A monster's `to_hit` is already the complete bonus its author
  intends; every other check resolves on the raw ability modifier.
- **No portrait field** on the seed character.
- **No speed, no challenge rating** on a stat block.

## 10. The rules a generator gets wrong by default

**A scene is facts, intentions and consequences, never a script.** Write what
is true (`truth`), what the creatures present want (`npc_intent`), and what
follows from plausible player action (`consequences`). Never write what the
player does, never write a branch, and never write dialogue the player must
hear verbatim.

**An exit condition is prose the agent judges, never a flag, a variable or a
comparison.** There is no flag store in this system, so there is nothing to
compare against. Write `"the bar has been broken, forced, or lifted from
outside"`. Never write `"alarm_raised == false"` or anything resembling it.

**A fixture's difficulty is an authored `dc`, never an improvised one.** The
DM judges checks against the numbers `checks[].dc` and `checks[].bypassed_by`
already give it; it never invents a target number, and it never decides at
runtime that some item not listed in `bypassed_by` should count.

## 11. A worked example

This is a minimal campaign, valid against every rule in §7. Reproduced
verbatim — copy from it directly. It is illustrative only; it is not shipped
as `backend/content/`. It is **two files** — the whole adventure, both its
scenes included, is one of them.

`campaigns/hollow-reach/v1/campaign.json`

```json
{
  "id": "hollow-reach",
  "title": "Hollow Reach",
  "summary": "A flooded valley, a mill that stopped turning, and a warden who will not say why.",
  "adventures": ["the-sunken-mill"],
  "seed_character": {
    "name": "Perrin Ashdown",
    "race": "Halfling",
    "character_class": "Rogue",
    "background": "A river-barge thief who owes the warden a favour and would rather not.",
    "appearance": "Small, weather-browned, with a river-knotted braid and a coat two sizes too large.",
    "abilities": {
      "strength": 9,
      "dexterity": 16,
      "constitution": 12,
      "intelligence": 11,
      "wisdom": 13,
      "charisma": 14
    },
    "max_hp": 9,
    "armour_class": 14,
    "inventory": ["belt-knife", "coil-of-rope", "tin-lantern"]
  },
  "object_templates": [
    {
      "id": "belt-knife",
      "kind": "item",
      "name": "Belt Knife",
      "description": "A small belaying knife Perrin keeps up a sleeve, more habit than weapon.",
      "attacks": [
        { "name": "Belt Knife", "to_hit": 3, "damage": "1d4" }
      ]
    },
    {
      "id": "coil-of-rope",
      "kind": "item",
      "name": "Coil of Rope",
      "description": "Ten yards of hemp rope, salt-stiffened from years on the barges."
    },
    {
      "id": "tin-lantern",
      "kind": "item",
      "name": "Tin Lantern",
      "description": "A dented tin lantern that throws more shadow than light but burns clean."
    },
    {
      "id": "bog-lurker",
      "kind": "creature",
      "name": "Bog Lurker",
      "description": "A flat, mottled thing the length of a man, all mouth and patience, indistinguishable from silt until it moves.",
      "disposition": "Ambush predator. Attacks anything that enters the water and retreats under it when badly hurt.",
      "stat_block": {
        "max_hp": 11,
        "armour_class": 13,
        "abilities": {
          "strength": 14,
          "dexterity": 13,
          "constitution": 12,
          "intelligence": 2,
          "wisdom": 11,
          "charisma": 4
        },
        "attacks": [
          { "name": "Bite", "to_hit": 4, "damage": "1d6+2" }
        ],
        "traits": ["Cannot be seen under still water without a deliberate search."]
      }
    },
    {
      "id": "rusty-key",
      "kind": "item",
      "name": "Rusty Key",
      "description": "A small iron key, pitted with rust, on a loop of waxed cord.",
      "attacks": []
    },
    {
      "id": "sunken-door",
      "kind": "fixture",
      "name": "Sunken Door",
      "description": "A swollen wooden door set into the flooded wall, warped shut by the water.",
      "checks": [
        {
          "action": "Force the swollen door with a shoulder",
          "dc": 14,
          "success": "The door gives way and the passage beyond stands open."
        },
        {
          "action": "Turn the lock with a key that still fits it",
          "dc": 8,
          "success": "The lock turns without a sound and the door swings open.",
          "bypassed_by": ["rusty-key"]
        }
      ]
    }
  ]
}
```

`campaigns/hollow-reach/v1/adventures/the-sunken-mill.json`

```json
{
  "id": "the-sunken-mill",
  "title": "The Sunken Mill",
  "intro": "The rain stopped three days ago and the water has not gone down. The mill at the bend has not turned since, and nobody who went to look has come back to say why.",
  "entry_scene": "mill-approach",
  "scenes": [
    {
      "id": "mill-approach",
      "title": "The Mill Approach",
      "truth": [
        "The mill leans into the flooded race; its wheel is jammed with black debris.",
        "The door is barred from the inside."
      ],
      "consequences": [
        "Breaking the bar is loud, and anything inside the mill hears it."
      ],
      "hidden": [
        {
          "fact": "Fresh bootprints lead into the mill and none lead out.",
          "dc": 12,
          "discovered_by": "a Wisdom (Perception) check on the mud, or searching the bank"
        }
      ],
      "placements": [
        { "template": "rusty-key", "count": 1 }
      ],
      "exits": [
        {
          "id": "into-the-mill",
          "to": "mill-floor",
          "description": "The mill door, barred from within.",
          "condition": "the bar has been broken, forced, or lifted from outside"
        }
      ]
    },
    {
      "id": "mill-floor",
      "title": "The Milling Floor",
      "truth": [
        "Knee-deep water covers the floor; the grain chute above is dry.",
        "Two bog lurkers have made the flooded floor their nest."
      ],
      "npc_intent": "The lurkers want to drag anything warm under the water and wait.",
      "consequences": [
        "Climbing to the dry grain chute puts the player out of the lurkers' reach."
      ],
      "placements": [
        { "template": "bog-lurker", "count": 2 },
        { "template": "sunken-door", "count": 1 }
      ],
      "exits": [
        {
          "id": "climb-out-through-the-chute",
          "kind": "adventure_end",
          "description": "The dry grain chute climbs past the wheel and out into open air."
        }
      ],
      "pressure": "The water is still rising; the chute will be the only dry footing within the hour."
    }
  ]
}
```

Why it is valid: the two scene ids are unique across the campaign (R8);
`mill-floor` is reachable from `mill-approach` (R11) and carries an
`adventure_end` exit, so the adventure has a way to end (R10); that exit
omits `to`, as an `adventure_end` exit must, and the reachability walk does
not try to follow it further (R11); every object template is referenced —
`bog-lurker` and `sunken-door` by a placement, `rusty-key` by a placement and
a `bypassed_by` entry, `belt-knife`/`coil-of-rope`/`tin-lantern` by
`seed_character.inventory` (R14) — and every name is unique (R15); no scene
places a template twice (R16); `sunken-door`'s second check is bypassed by
`rusty-key`, an `item`-kind template (R17); each seed-character inventory
entry names a declared `item`-kind template (R20); each scene has only one
exit, so trivially no two exits in the same scene share an id (R19); the
omitted optional fields — `npc_intent`, `placements`, `pressure` on
`mill-approach`, `kind` on `into-the-mill` (defaulting to `scene`), and
`condition` on `climb-out-through-the-chute` — take their defaults; `to` is
correctly absent on `climb-out-through-the-chute`, since an `adventure_end`
exit must not carry one.

## 12. Authoring checklist

Run down this list before validating:

- [ ] Every scene of every adventure is reachable from that adventure's
      `entry_scene` by following exits.
- [ ] Some scene reachable from `entry_scene` carries an `adventure_end`
      exit.
- [ ] Every `scene`-kind exit names a `to`; every `adventure_end`-kind exit
      omits it.
- [ ] No two exits in the same scene share an `id`.
- [ ] Every object template is referenced by at least one placement, one
      carry, one `bypassed_by` entry, or one `seed_character.inventory`
      entry.
- [ ] Every `seed_character.inventory` entry names a declared **item**-kind
      template, never free text.
- [ ] No scene places the same template twice in `placements`, and no
      placement carries the same template twice in `carries` — use `count`
      instead.
- [ ] Every object template's `name` is unique across the campaign, ignoring
      case, across all three kinds.
- [ ] Every scene id is unique across the whole campaign, not just its own
      adventure.
- [ ] Every `bypassed_by` entry names an `item`-kind template, never a
      creature or a fixture.
- [ ] Every `carries[].template` names an `item`-kind template; an `item`
      placement never carries anything itself.
- [ ] Every id (`campaign.id`, adventure/scene/template ids) matches its own
      filename stem where it has one (or, for a scene or a template, is
      unique campaign-wide; for an exit, is unique within its own scene) and
      is lowercase kebab-case.
- [ ] Every prose field carries real text — no accidental whitespace-only
      string.
- [ ] The player-class key is `character_class`, and the armour key is
      `armour_class`.

Then run `app content validate`.
