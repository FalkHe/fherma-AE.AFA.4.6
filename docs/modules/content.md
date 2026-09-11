# Adventure content — the authoring guide

This is the complete reference for authoring a campaign. It is written so that
an author with **no access to the schema code** can produce a campaign tree
that `app content validate` accepts on the first run: every field, every
constraint that rejects a file, and every referential rule is stated here, not
merely implied.

## 1. What content is and what it is not

Content is **hand-authored, version-pinned, static JSON checked into git**,
read-only at runtime. A run references a campaign by its id and a pinned
version and never sees any other version, even after the campaign is extended.
Content is **not** a database, **not** a script that decides what the player
does, and **not** generated at runtime — there is no content-generation CLI in
this stage; this document is the only authoring aid.

## 2. Directory layout

```
backend/content/
└── campaigns/
    └── <campaign_id>/
        └── <version>/
            ├── campaign.json
            ├── adventures/<adventure_id>.json
            └── definitions/<definition_id>.json
```

Example: `backend/content/campaigns/hollow-reach/v1/campaign.json`.

A campaign version is exactly **three kinds of file**:

- `campaign.json` — the campaign's metadata and its seed player character.
- `adventures/<adventure_id>.json` — **the whole adventure, its scenes
  included, inline.** There is no `scenes/` directory and no separate scene
  file.
- `definitions/<definition_id>.json` — one file per campaign-scoped NPC or
  monster template.

**Why the granularity is what it is.** A scene belongs to exactly one
adventure and cannot be shared or orphaned, so it lives inside that
adventure's file. A definition is campaign-scoped — the villain of adventure 1
can return in adventure 3 — so it cannot live inside any one adventure and
stays its own file. The campaign's own metadata and its seed character are
neither, and stay in `campaign.json`.

- **Only `*.json` files are considered.** A `README.md`, a `.DS_Store` or an
  editor swap file sitting inside `adventures/` or `definitions/` is ignored
  entirely — never read, never reported as an orphan.
- **A missing `adventures/` or `definitions/` directory is treated as an
  empty directory**, not an error by itself — but an adventure or definition
  that `campaign.json` or a scene expects and does not find still fails the
  referential rules below (§7).

## 3. Versioning

A version is a directory literally named `v<n>` — `v1`, `v2`, and so on — a
digit sequence with no leading `v` missing and no decimal point. A version is
never edited in place once it exists: content is extended by **copying the
whole tree to `v2` and editing there**, so a run pinned to `v1` stays
reproducible forever. There is no manifest, no semantic version and no
`published` flag — the directory name is the only version record there is.

## 4. Casing and naming rules

These are the mistakes an author (or a generator) makes by default. Each is a
rule, not a suggestion:

- **JSON keys are `snake_case`** and identical, letter for letter, to the field
  names in this document. There is no camelCase anywhere in content.
- **Every id is lowercase kebab-case**: `^[a-z0-9]+(-[a-z0-9]+)*$` — lowercase
  letters, digits and single hyphens between segments. `Bog-Lurker`, `bog_lurker`
  and `bog--lurker` are all rejected.
- **The player-class field's JSON key is `character_class`, not `class`.**
  `class` is a Python reserved word; the schema never uses it.
- **The armour-class field's JSON key is `armour_class`, not `armor_class`.**
  The project's glossary pins the British spelling and content uses it exactly.

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

One attack a stat block can make.

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `name` | prose string | yes | — | The attack's name, shown to the player |
| `to_hit` | integer | yes | — | The **complete** bonus added to the d20 — already includes any proficiency the author intends; nothing is added on top |
| `damage` | prose string | yes | — | A dice expression, e.g. `"1d6+2"`, passed verbatim to the dice roller — not validated by content loading |

### 5.3 `StatBlock`

Carried by **every** `Definition` and by the `SeedCharacter`'s inline fields
(§5.10). It is what makes an entity able to exist as a mechanical creature.

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

### 5.4 `Definition`

One entity used for both NPCs and monsters — there is no npc/monster split.
Campaign-scoped: a definition may recur across every adventure of the
campaign. File: `definitions/<id>.json` — the one file in the tree that
belongs to no single adventure.

**What a `Definition` is, and why the word is `Definition`.** A definition is
a **template**: the campaign-scoped description of a kind of creature. What
appears in a scene during a run is an **instance** of it — a creature with
current hit points, an aliveness flag and its own disposition, created fresh
each time the scene is populated. `Scene.creatures` entries point at a
`definition` by id; the directory that holds the templates is `definitions/`.
Follow that one word — `definition` — from the placement to the file.

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `id` | content id | yes | — | Must equal the filename stem |
| `name` | prose string | yes | — | Player-facing name; **must be unique within the campaign, case-insensitively** (R15) |
| `description` | prose string | yes | — | Who they are, what they look like |
| `disposition` | prose string | yes | — | What they want, how they treat the player |
| `stat_block` | `StatBlock` | yes | — | **Required on every definition** — a definition with no stat block does not exist in this schema |

### 5.5 `Secret`

One entry of a scene's `hidden` list — a fact the DM knows and the player must
earn.

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `fact` | prose string | yes | — | What is true but not apparent |
| `dc` | integer, 1–30 | yes | — | The target number to discover it |
| `discovered_by` | prose string | yes | — | Prose describing the ability/skill and the action that reveals it, e.g. `"a Wisdom (Perception) check on entering, or searching the crates"` — not a skill enum |

`hidden` and `dc` are DM-only and must never be shown to the player.

### 5.6 `CreaturePlacement`

One entry of a scene's `creatures` list.

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `definition` | content id | yes | — | The id of a `Definition` this scene places |
| `count` | integer, ≥1 | no | `1` | How many instances of that definition appear |

**A definition may appear at most once in a scene's `creatures` list** (R16):
write `{"definition": "goblin", "count": 3}` for three goblins, never three
separate entries.

### 5.7 `Exit`

One entry of a scene's `exits` list — **a list, not a map**.

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `to` | content id | yes | — | The id of a scene in the **same adventure** |
| `description` | prose string | yes | — | What the player perceives as the way on |
| `condition` | prose string or `null` | no | `null` | Prose the DM judges before allowing the exit; `null` means always open |

**A scene with `exits: []` is terminal** — reaching it ends the adventure.
Every adventure must have at least one terminal scene (R10).

### 5.8 `Scene`

**A scene is not a file.** It is an element of its adventure's `scenes` list
(§5.9), so a scene belongs to exactly one adventure and cannot be orphaned or
shared between adventures. It keeps its own `id`, which is how exits, runs and
the loaded campaign's flat scene map address it. Facts, intentions and
consequences — never a script (see §10).

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `id` | content id | yes | — | Unique across the **whole campaign** (R8), not just the adventure |
| `title` | prose string | yes | — | Short location label, shown to the player |
| `truth` | list of prose strings, min length 1 | yes | — | What is true here — at least one fact is required |
| `npc_intent` | prose string or `null` | no | `null` | What the creatures present want; `null` when the scene has no creatures |
| `consequences` | list of prose strings | no | `[]` | What follows from plausible player action — never what the player does |
| `hidden` | list of `Secret` | no | `[]` | DM-only secrets |
| `creatures` | list of `CreaturePlacement` | no | `[]` | Who is here |
| `exits` | list of `Exit` | no | `[]` | Ways out of the scene; empty means terminal |
| `pressure` | prose string or `null` | no | `null` | What forces the scene forward |

### 5.9 `Adventure`

File: `adventures/<id>.json` — **the whole adventure, its scenes included.**

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `id` | content id | yes | — | Must equal the filename stem |
| `title` | prose string | yes | — | Player-facing title |
| `intro` | prose string | yes | — | Prose read aloud when the adventure starts |
| `entry_scene` | content id | yes | — | Must be the id of one of this adventure's own `scenes` |
| `scenes` | list of `Scene`, min length 1 | yes | — | The scenes themselves, inline — not ids. Order is authoring convenience only; traversal is defined by exits and `entry_scene` |

### 5.10 `SeedCharacter`

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
| `inventory` | list of prose strings | no | `[]` | Starting items, as free text |

No `portrait` field, no `level`, no proficiency, no authored attacks — see §9.
The seed character references nothing else in content, so there is no
referential rule for it.

### 5.11 `Campaign`

File: `campaign.json`.

| JSON key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `id` | content id | yes | — | Must equal the campaign's directory name |
| `title` | prose string | yes | — | Player-facing title |
| `summary` | prose string | yes | — | The pitch, shown when a run starts |
| `adventures` | list of content ids, min length 1 | yes | — | **Ordered** — the play order |
| `seed_character` | `SeedCharacter` | yes | — | The starting player character |

There is no `version` field: the version is the directory name and nothing
else, so the two can never disagree.

## 6. Every constraint that actually rejects a file

- **Unknown keys are rejected, not ignored.** Every model forbids extra
  properties; a typo in a key name is a loud load error.
- **Every id must match `^[a-z0-9]+(-[a-z0-9]+)*$`.**
- **Every prose string is stripped of surrounding whitespace and must then be
  non-empty.** `"   "` is rejected — it strips to the empty string.
- **Numeric bounds**: every ability score is 1–30; every `dc` is 1–30; `max_hp`
  and `armour_class` are ≥1; `CreaturePlacement.count` is ≥1.
- **List minimums**: `Scene.truth` needs at least one entry; `Adventure.scenes`
  and `Campaign.adventures` need at least one entry each.
- No string and no list has an upper bound — nothing here rejects a file for
  being long.

## 7. The referential rule list

Applied after every file in the tree has already passed the field checks
above. Each rule's tag is what appears in a validation error, in the form
`<path>: [<TAG>] <detail>` (§8) — an author who sees `[R11]` can look the
number up here. **Sixteen rules, `R1` through `R16`; R1 carries no tag of its
own.**

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
| R9 | loader | Every `exit.to` names a scene in the **same** adventure, and is never the scene's own id |
| R10 | loader | Each adventure has at least one scene whose `exits` is `[]` |
| R11 | loader | Every scene of an adventure is reachable from `entry_scene` by following exits (conditions ignored for this check); the entry scene itself counts as reached |
| R12 | loader | Every `creatures[].definition` resolves to a `definitions/<id>.json` |
| R13 | loader | Each definition's `id` equals its own filename stem |
| R14 | loader | Every `*.json` file in `definitions/` is referenced by at least one scene — no dead content |
| R15 | loader | `Definition.name` is unique across the campaign, compared case-insensitively after stripping — `"Bog Lurker"` and `"bog lurker"` collide |
| R16 | loader | A definition appears at most once in a single scene's `creatures` list |

**What an id/filename mismatch gets you.** An entity is always identified by
its **filename**, never by the `id` field inside the file, so a mismatch never
changes what the entity is called elsewhere in the tree — it only earns a
report:

- An **adventure** whose `id` disagrees with its filename (`[R6]`) is dropped:
  it produces no other findings about itself, and its scenes are reported by
  nothing — they are not files and cannot be orphans.
- A **definition** whose `id` disagrees with its filename (`[R13]`) is
  reported but not dropped: it is still checked against every other rule under
  its filename, so fixing the `id` alone is enough — there is nothing else to
  redo.
- A **scene** has no filename, so its identity is its `id` field; `R8` is
  what keeps that identity unambiguous across the whole campaign.

**What one broken adventure does to the rest of the report.** An adventure
that fails `[R6]`, `[READ]` or `[SCHEMA]` is dropped whole: it is excluded from
every later rule and produces no further findings about itself, and its scenes
go with it. **A dropped adventure contributes no scenes to R14**, so a
definition that only that adventure referenced is reported `[R14]` as
unreferenced — this is the deliberate answer, not an oversight. Fix the
adventure and the `[R14]` disappears on its own; there is nothing else to do
about it.

`seed_character` has no referential rule — it references nothing else in
content.

## 8. The message grammar and exit codes

Every reported problem has the shape:

```
<path relative to the version directory>: [<TAG>] <detail>
```

- `[READ]` — the file could not be read, or is not valid JSON.
- `[SCHEMA]` — the file parsed as JSON but failed a field check (§6).
- `[R2]` … `[R16]` — the numbered referential rule that failed (§7). **R1 has
  no tag of its own** — its failure is always reported as `[READ]` or
  `[SCHEMA]` against `campaign.json`. **R3 never appears here** — it is a
  CLI-level check, not a loader rule.

**A rule that fails inside a scene names its adventure file** — a scene is not
its own file, so the message is against `adventures/<id>.json` — and puts the
scene id in the detail so the place in it can still be found.

Example messages:

```
adventures/the-sunken-mill.json: [R9] scene 'mill-approach': exit targets unknown scene 'under-whee'
adventures/the-sunken-mill.json: [SCHEMA] scenes.1.truth.0: String should have at least 1 character
campaign.json: [SCHEMA] Input should be a valid dictionary
definitions/bog-lurker.json: [READ] Expecting ',' delimiter: line 8 column 3 (char 214)
```

Running `app content validate` checks every campaign and every version found
under the content root:

| Exit code | Condition |
|---|---|
| `0` | At least one campaign version was found, every one is valid, no non-conformant version directory exists, and every campaign has at least one conformant version |
| `1` | Any campaign version failed validation, any version directory name is non-conformant (`[R3]`), any campaign has no conformant version directory, or no campaign was found at all |

## 9. What the schema deliberately does not carry

Do not try to add these — they have no field:

- **No items and no fixtures as content entities.** A scene's occupants are
  creatures only (`creatures[]`); loot and scenery are narrated, not declared.
- **No level, no proficiency bonus, no skill list, no authored player
  attacks.** A monster's `to_hit` is already the complete bonus its author
  intends; every other check resolves on the raw ability modifier.
- **No portrait field** on the seed character.
- **No speed, no challenge rating** on a stat block.

## 10. The two rules a generator gets wrong by default

**A scene is facts, intentions and consequences, never a script.** Write what
is true (`truth`), what the creatures present want (`npc_intent`), and what
follows from plausible player action (`consequences`). Never write what the
player does, never write a branch, and never write dialogue the player must
hear verbatim.

**An exit condition is prose the agent judges, never a flag, a variable or a
comparison.** There is no flag store in this system, so there is nothing to
compare against. Write `"the bar has been broken, forced, or lifted from
outside"`. Never write `"alarm_raised == false"` or anything resembling it.

## 11. A worked example

This is a minimal campaign, valid against every rule in §7. Reproduced
verbatim — copy from it directly. It is illustrative only; it is not shipped
as `backend/content/`. It is **three files** — the whole adventure, both its
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
    "inventory": ["a shortsword", "a coil of rope", "a tin lantern"]
  }
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
      "exits": [
        {
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
      "creatures": [
        { "definition": "bog-lurker", "count": 2 }
      ],
      "pressure": "The water is still rising; the chute will be the only dry footing within the hour."
    }
  ]
}
```

`campaigns/hollow-reach/v1/definitions/bog-lurker.json`

```json
{
  "id": "bog-lurker",
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
}
```

Why it is valid: the two scene ids are unique across the campaign (R8);
`mill-floor` is reachable from `mill-approach` (R11) and has no `exits`, so it
is terminal (R10); `bog-lurker` is referenced by a scene (R14) and its name is
unique (R15); no scene places a definition twice (R16); the omitted optional
fields — `npc_intent`, `creatures`, `pressure` on `mill-approach`, and `exits`
on `mill-floor` — take their defaults, which is legal and is how absence is
expressed.

## 12. Authoring checklist

Run down this list before validating:

- [ ] Every scene of every adventure is reachable from that adventure's
      `entry_scene` by following exits.
- [ ] Every adventure has at least one scene with `exits: []`.
- [ ] Every definition is referenced by at least one scene.
- [ ] No scene places the same definition twice — use `count` instead.
- [ ] Every definition's `name` is unique across the campaign, ignoring case.
- [ ] Every scene id is unique across the whole campaign, not just its own
      adventure.
- [ ] Every id (`campaign.id`, adventure/scene/definition ids) matches its own
      filename stem (or, for a scene, is unique campaign-wide) and is
      lowercase kebab-case.
- [ ] Every prose field has real content — no accidental whitespace-only
      string.
- [ ] The player-class key is `character_class`, and the armour key is
      `armour_class`.

Then run `app content validate`.
