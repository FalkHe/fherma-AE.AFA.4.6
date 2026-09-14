---
title: "Step 1.4 — The object-template rework"
stage: 1
phase: 1
step: 1.4
status: spec
created: 2026-09-14
human_in_the_loop: true
---

# Step 1.4 — The object-template rework

**A rework of phase 1's already-landed Campaign-Definition schema, not a new
phase** (owner ruling). Four owner decisions — P1-D22 (items and fixtures are
declared), P1-D23 (the entity is `ObjectTemplate`), P1-D24 (two kinds of file,
templates in `campaign.json`) and P1-D25 (carried-at-start placement) — are
turned into a build-ready contract here: exact models, exact JSON shapes, exact
rule set, exact acceptance criteria.

**This file is the authority wherever it and
[`shared-knowledge.md`](shared-knowledge.md) differ.** That document's §0.0
lists exactly which of its sections this one supersedes; everything else in it
still binds, including every landed decision and every convention of its §3.0.

**Depends on steps 1.1, 1.2 and 1.3, all landed.** It rewrites part of each.

**Human in the loop: yes, for one thing only** — §5 reworks Greenhollow's
Story: six new object templates and a handful of reworded scene lines, so the
new mechanics are motivated by the narrative rather than bolted onto it. Prose
is never judged by an agent. The owner's approval of *this spec* is that
acceptance: every new and reworded line is written out in §5 in full, and
backend-dev copies it verbatim. No agent writes, improves or rewords Greenhollow
prose in this step.

---

## 1. Scope

In scope:

| Area | What changes |
|---|---|
| `backend/app/modules/content/schemas.py` | `Definition` → the `ObjectTemplate` union; `CreaturePlacement` → `Placement` + `Carried`; `Scene.creatures` → `Scene.placements`; `Campaign.object_templates`; `LoadedCampaign.object_templates` |
| `backend/app/modules/content/service.py` | Templates load from `campaign.json` instead of `definitions/*.json`; `load_definition` → `load_object_template`; rules R12–R18 |
| `backend/content/campaigns/greenhollow/v1/**` | The tree reworked to §5 — nine object templates, the reworded Story lines, the new placements, and the deletion of `definitions/` |
| `docs/modules/content.md` | The authoring guide reworked to this contract |
| `docs/general/glossary.md` | One parenthetical struck (§9) |
| `backend/tests/content/**` | qa-backend re-authors against this contract |

Out of scope, and a deviation if it appears:

- **A second placement axis, a container hierarchy or recursive carrying.**
  `carries` is one level deep and its entries carry nothing (P1-D25).
- **Hit points or armour class on an item or a fixture.** A fixture's difficulty
  is its `checks[].dc`; that is the whole of it (§3.6).
- **Converting `SeedCharacter.inventory` to item-template references.** P1-D26
  defers it explicitly. `inventory: list[ProseText]` is unchanged, field for
  field.
- **Any Story change other than the ones §5 prints verbatim.** The owner has
  lifted step 1.3's "byte-identical prose" fence for this step (P1-D27), so the
  reworked scene lines of §5.2 *are* in scope — but only those. The three
  creature templates' prose and numbers, `campaign.json`'s metadata, the seed
  character, the scene ids, titles, order, `hidden`, `exits` and `pressure` are
  all unchanged, and inventing a line §5 does not print is a deviation.
- A second campaign, a second adventure, a second content version, a `v2`.
- Any HTTP route, database table, migration, frontend file, i18n key or
  environment variable. Phase 1 still lands none of these.

---

## 2. Environment you will meet

- The Docker stack is **down**. `.env` exists (`cp .env.dist .env` if not);
  `.env.dist` is owner-only.
- Alembic head is `0001`. **This step adds no migration.** The `objects` table
  does not exist yet — §8's `model.md` delta is a *note for phase 5*, already
  applied to the document, with no schema work in this step.
- `backend/app/modules/content/` is at its step-1.1 state: `Definition`,
  `CreaturePlacement`, `Scene.creatures`, rules R1–R16, `load_definition`.
- `backend/content/campaigns/greenhollow/v1/` holds `campaign.json`,
  `adventures/goblins-of-greenhollow.json` (four scenes inline) and
  `definitions/` with `mira.json`, `goblin.json`, `goblin-boss.json`.
- **`app content validate` currently exits `0`** with `greenhollow/v1: ok` on
  stdout. It must exit `0` again when this step is done. **It will exit `1`
  between the schema change and the tree migration; that red is the rework
  working**, exactly as in the P1-D20 pass, and no agent is to repair it by
  relaxing the schema.
- `backend/tests/content/` holds `conftest.py`, `test_schemas.py`,
  `test_service.py`, `test_cli.py`, `test_shipped_tree.py`, all currently green.

---

## 3. The schema

`backend/app/modules/content/schemas.py`. Every convention of
`shared-knowledge.md` §3.0 is unchanged and binds: `ContentModel` with
`extra="forbid"` and `frozen=True`, `snake_case` JSON keys identical to the
Python field names, `ContentId` for ids, `ProseText` for human-readable strings,
British spelling, no upper bounds.

Unchanged models, not restated here: `Abilities`, `Attack`, `StatBlock`,
`Secret`, `Exit`, `Adventure`, `SeedCharacter`.

### 3.1 `ObjectTemplate` — a `kind`-discriminated union

The campaign-scoped blueprint of one thing a scene can contain. Each placement
of it becomes one `objects` row when a run starts (`model.md`). One shared head,
three tails, each tail carrying exactly what the mechanics layer needs to
resolve an interaction against that kind — and nothing else.

```python
class ObjectTemplateBase(ContentModel):
    id: ContentId
    kind: str
    name: ProseText
    description: ProseText


class CreatureTemplate(ObjectTemplateBase):
    kind: Literal["creature"]
    disposition: ProseText
    stat_block: StatBlock


class ItemTemplate(ObjectTemplateBase):
    kind: Literal["item"]
    attacks: list[Attack] = Field(default_factory=list)


class FixtureTemplate(ObjectTemplateBase):
    kind: Literal["fixture"]
    checks: list[FixtureCheck] = Field(min_length=1)


ObjectTemplate = Annotated[
    CreatureTemplate | ItemTemplate | FixtureTemplate,
    Field(discriminator="kind"),
]
```

`ObjectTemplate` is a type alias, not a class: it is what `Campaign` and
`LoadedCampaign` are annotated with, and it is the name every document and every
agent uses for the entity.

**The shared head**

| Field | JSON key | Type | Required | Default | What it is for |
|---|---|---|---|---|---|
| `id` | `id` | `ContentId` | yes | — | How a placement, a carry and a `bypassed_by` **entry** name it. Unique within the campaign (R13) |
| `kind` | `kind` | `"creature" \| "item" \| "fixture"` | yes | — | The discriminator. Exactly `model.md`'s three object kinds, same spellings |
| `name` | `name` | `ProseText` | yes | — | Player-facing. Unique within the campaign, case-insensitively (R15) |
| `description` | `description` | `ProseText` | yes | — | What it is and what it looks like. DM-prompt material |

**`CreatureTemplate` — the former `Definition`, field for field**

| Field | JSON key | Type | Required | Default | What it is for |
|---|---|---|---|---|---|
| `disposition` | `disposition` | `ProseText` | yes | — | What it wants and how it treats the player; seeds the object state blob's disposition |
| `stat_block` | `stat_block` | `StatBlock` | yes | — | Required on every creature (P1-D3). `attacks: []` is what "cannot fight" means |

**`ItemTemplate`**

| Field | JSON key | Type | Required | Default | What it is for |
|---|---|---|---|---|---|
| `attacks` | `attacks` | `list[Attack]` | no | `[]` | What the item offers whoever wields it. `[]` is an ordinary object with no combat use |

**`FixtureTemplate`**

| Field | JSON key | Type | Required | Default | What it is for |
|---|---|---|---|---|---|
| `checks` | `checks` | `list[FixtureCheck]` | yes | — | `min_length=1`. Every authored way to act on the fixture, each with the DC the DM must not invent |

A fixture with no checks is scenery, and scenery is narrated in `truth` rather
than instantiated — so `min_length=1` is what separates the two. An item may
legitimately have no attacks, so its list defaults to empty; a fixture may not
legitimately have no checks, so its list has no default at all.

**`FixtureCheck`**

```python
class FixtureCheck(ContentModel):
    action: ProseText
    dc: int = Field(ge=1, le=30)
    success: ProseText
    bypassed_by: list[ContentId] = Field(default_factory=list)
```

| Field | JSON key | Type | Required | Default | What it is for |
|---|---|---|---|---|---|
| `action` | `action` | `ProseText` | yes | — | What a character *does*, in prose a player who does not know the rules can follow — not a skill enum (the `Secret.discovered_by` precedent) |
| `dc` | `dc` | `int`, 1–30 | yes | — | The authored target number. "The dice are real" requires the author to supply it |
| `success` | `success` | `ProseText` | yes | — | What is true afterwards. Facts, never narration to be recited |
| `bypassed_by` | `bypassed_by` | `list[ContentId]` | no | `[]` | The ids of the **`item`**-kind templates that make this check succeed with no roll. **Holding any one of them is enough** (R12, R17). `[]` means nothing bypasses it |

`bypassed_by` is the key-for-the-lock and the blade-for-the-rope. Each entry
names a template, never an instance and never a condition — there is no flag
store (P1-D6), and the DM's question is only "does the character hold one of
these".

**It is a list, and `[]` is the only way to say "nothing bypasses this"**
(owner ruling). A single optional id was too narrow: "cut the lashings" should
accept a knife, a sword or any other blade the campaign declares, and one
authored id cannot say that. The list is **disjunctive** — it is an *any-of*,
never an all-of — and it is **explicit**: the eligible items are enumerated by
the author, never inferred by the DM from an item's description or name. That
is the deterministic-mechanics principle applied here; a narrator deciding at
runtime that a horseshoe is sharp enough is exactly what the authored list
exists to prevent.

There is **no `None`**. An absent key, an explicit `[]` and "no shortcut" are one
value and one representation, so there is no second way to express it and no
null check anywhere downstream. A new item that ought to satisfy an existing
check is added to that check's list by hand; that bookkeeping cost is accepted
and is a content-authoring concern, not a schema defect.

**Rejecting a wrong-kind field is the point.** `extra="forbid"` is inherited, so
an `ItemTemplate` carrying `stat_block`, a `CreatureTemplate` carrying `checks`
and a `FixtureTemplate` carrying `attacks` are all loud `[SCHEMA]` failures, and
a template with an unknown or missing `kind` fails on the discriminator. Nothing
in this union is a bag of optional fields (P1-D22, reason 3).

### 3.2 `Placement` and `Carried`

```python
class Carried(ContentModel):
    template: ContentId
    count: int = Field(default=1, ge=1)


class Placement(ContentModel):
    template: ContentId
    count: int = Field(default=1, ge=1)
    carries: list[Carried] = Field(default_factory=list)
```

| Field | JSON key | Type | Required | Default | What it is for |
|---|---|---|---|---|---|
| `Placement.template` | `template` | `ContentId` | yes | — | The `ObjectTemplate` id this placement instantiates (R12) |
| `Placement.count` | `count` | `int ≥ 1` | no | `1` | How many `objects` rows phase 5 creates. Covers a named NPC (`1`) and a monster group identically |
| `Placement.carries` | `carries` | `list[Carried]` | no | `[]` | What **each** instance this placement creates owns at spawn |
| `Carried.template` | `template` | `ContentId` | yes | — | An **`item`**-kind template id (R12, R17) |
| `Carried.count` | `count` | `int ≥ 1` | no | `1` | How many of it each owning instance holds |

**`carries` is per created instance, not per placement.** `{"template":
"goblin", "count": 3, "carries": [{"template": "sling"}]}` is three goblins with
one sling each, which is what an author means and what 5e stat blocks express.
Three goblins sharing one sling is not expressible, and does not need to be.

**Who may carry (P1-D25, owner-confirmed).** A `creature` placement and a
`fixture` placement may both carry: a boss holding a key and a sack holding
fleeces are the same mechanic. **A placement whose template kind is `item` has
empty `carries`** (R18) — an item does not itself carry anything.

**One level deep, never recursive.** A `Carried` entry has no `carries` of its
own — `extra="forbid"` rejects one — so the authored containment tree is exactly
two levels and phase 5's instantiation is one nested loop, not a walk.

### 3.3 `Scene` — one field renamed, nothing else

```python
class Scene(ContentModel):
    id: ContentId
    title: ProseText
    truth: list[ProseText] = Field(min_length=1)
    npc_intent: ProseText | None = None
    consequences: list[ProseText] = Field(default_factory=list)
    hidden: list[Secret] = Field(default_factory=list)
    placements: list[Placement] = Field(default_factory=list)   # was: creatures
    exits: list[Exit] = Field(default_factory=list)
    pressure: ProseText | None = None
```

`creatures` becomes `placements` because the list no longer holds creatures.
There is no compatibility alias and no transitional acceptance of the old key:
`extra="forbid"` means an un-migrated file fails loudly, which is the behaviour
this schema exists for.

`npc_intent` keeps its name and its meaning — *what the creatures present want*
— and stays `None` in a scene with no creature placements. It is not widened to
cover fixtures; a fixture has no intent.

### 3.4 `Campaign` — templates move in (P1-D24)

```python
class Campaign(ContentModel):
    id: ContentId
    title: ProseText
    summary: ProseText
    adventures: list[ContentId] = Field(min_length=1)
    seed_character: SeedCharacter
    object_templates: list[ObjectTemplate] = Field(min_length=1)
```

`object_templates` is a **list**, not a map: the id is already on each element,
and a map would give the same value two homes and let them disagree. Its order
is authoring convenience and carries no meaning; `LoadedCampaign` preserves it
only so output is stable.

`min_length=1` — a campaign that declares no templates places nothing and
instantiates nothing, which is a truncated file rather than an intention, and it
mirrors `adventures`.

`seed_character` is unchanged, including `inventory: list[ProseText]` (P1-D26).

### 3.5 `LoadedCampaign`

```python
class LoadedCampaign(ContentModel):
    campaign: Campaign
    version: str
    adventures: dict[str, Adventure]
    scenes: dict[str, Scene]
    object_templates: dict[str, ObjectTemplate]   # keyed by id, in campaign.object_templates order
```

Only the last field changes — `definitions` is renamed and re-keyed by the `id`
field rather than by a filename stem, because there is no longer a file. No
consumer exists yet (phases 5, 7 and 8 are unbuilt), so there is nothing to
migrate and no alias to keep.

R15 still makes a lookup by display name over `object_templates.values()` well
defined, now across all three kinds.

### 3.6 What the union deliberately does not carry

Named here so no implementer quietly adds one:

- **No hit points and no armour class on an item or a fixture.** A fixture's
  resistance is authored as a `checks[].dc`; a door that can be smashed is a
  check whose `action` is smashing it. Adding HP/AC would create a second
  mechanic for the same question and force `model.md`'s promoted columns to be
  meaningful for non-creatures.
- **No weight, no value, no stack size, no slot.** There is no inventory
  economy in Stage-01 and no consumer for any of them.
- **No `consumable`, `quantity` or durability on `ItemTemplate`.** Quantity
  lives on the placement (`count`), and everything else is a phase-5 state-blob
  question about an *instance*, not a property of the template.
- **No `locked` / `open` state on `FixtureTemplate`.** A template is
  immutable and read-only; state belongs to the instance.

---

## 4. The content tree — two kinds of file

```
backend/content/
└── campaigns/
    └── <campaign_id>/
        └── <version>/
            ├── campaign.json                   # metadata + seed_character + object_templates[]
            └── adventures/<adventure_id>.json  # the adventure and its scenes, inline
```

**There is no `definitions/` directory and no `scenes/` directory.** Granularity
follows scope: a scene belongs to exactly one adventure and lives inside it
(P1-D20); an object template is campaign-scoped and lives in the
campaign-scoped file (P1-D24).

Everything else in `shared-knowledge.md` §4 is unchanged: only `*.json` under
`adventures/` is considered, a missing `adventures/` directory is an empty
directory rather than an exception, and a version is a `v<n>` directory served
whole and never edited in place.

---

## 5. The canonical worked example — the reworked Greenhollow tree

This section is **both** the normative shape example and the exact target state
for `backend/content/campaigns/greenhollow/v1/`. Field names, casing, nesting,
ordering **and every line of prose printed here** are normative. backend-dev
copies them character for character and writes no prose of its own.

**The Story fence is lifted for this step (owner ruling).** Step 1.3's
"byte-identical prose" constraint does not apply here: the campaign is reworked
so that the new object templates are motivated by the narrative rather than
bolted onto it. What is reworked is pinned below, line by line; what is not
printed below is unchanged.

### 5.0 What the shipped tree must demonstrate

The owner's completeness bar: **no schema mechanism ships unexercised.** Each
row below is proved by the content of §5.1 and §5.2, and criterion 27a of §10
checks it.

| Mechanism | Proved by | Where |
|---|---|---|
| `CreatureTemplate` | `mira`, `goblin`, `goblin-boss` | `campaign.json` |
| `ItemTemplate` with a non-empty `attacks` | `shepherds-knife`, `notched-cleaver` | `campaign.json` |
| `ItemTemplate` with `attacks: []` | `bent-horseshoe`, `stolen-fleece` | `campaign.json` |
| `FixtureTemplate` | `thorn-screen`, `wool-sack` | `campaign.json` |
| A **creature** placement that carries | `goblin-boss` carries `notched-cleaver`; `mira` carries `shepherds-knife` | scenes `lair-hollow`, `village-green` |
| A **fixture** placement that carries | `wool-sack` carries `stolen-fleece` × 2 | scene `lair-hollow` |
| A **bare item** placement — no carrier, `carries` omitted | `bent-horseshoe` | scene `village-green` |
| A `carries` entry with `count > 1` | `stolen-fleece`, `count: 2` | scene `lair-hollow` |
| A placement with `count > 1` | `goblin`, `count: 3` | scene `lair-maw` |
| A scene with **no** placements | `placements: []` | scene `thornway` |
| `bypassed_by` → a **cross-scene** item chain | `thorn-screen`'s cut check lists `shepherds-knife`, which Mira carries two scenes earlier | `campaign.json` + scenes `village-green`, `lair-maw` |
| `bypassed_by` → a **same-scene** item chain | `wool-sack`'s cut check lists `notched-cleaver`, which Grettle carries in that scene | `campaign.json` + scene `lair-hollow` |
| A **multi-item** `bypassed_by` — any one of two blades satisfies it | `thorn-screen`'s cut check lists `shepherds-knife` **and** `notched-cleaver` | `campaign.json` |
| A **single-item** `bypassed_by` — a list of one | `wool-sack`'s cut check lists `notched-cleaver` only | `campaign.json` |
| A `checks[]` entry with **no** `bypassed_by` key, defaulting to `[]` | the first check of each fixture | `campaign.json` |
| A fixture with more than one check | both fixtures carry two | `campaign.json` |

Both bypass chains are **playable, not merely structurally valid**: at least one
listed item is in the player's reach before the check is met — Mira presses the
shepherd's knife on the player at the green, and Grettle's cleaver is lootable in
the hollow the sack hangs in.

`thorn-screen`'s second entry is the multi-item case the schema exists for: the
knife is the intended route and is reachable before the screen, and the cleaver
is the second blade the campaign happens to declare, eligible for anyone who has
taken it. `wool-sack`'s second entry stays a **list of one** on purpose — the
authored action is splitting the sack with a *heavy* blade, and the knife is not
one — so the shipped tree proves both cardinalities.

### 5.1 `campaign.json`

`id`, `title`, `summary`, `adventures` and the whole of `seed_character` are
**unchanged, byte for byte**. One key is appended: `object_templates`, holding
nine entries in this order — the three migrated creature templates in their
landed order, then the four items, then the two fixtures.

Each migrated creature template is its former `definitions/<id>.json` body with
**`"kind": "creature"` inserted after `id`** and nothing else touched — same
`id`, same `name`, same `description`, same `disposition`, same `stat_block`,
same numbers, same wording.

```json
{
  "id": "greenhollow",
  "title": "Greenhollow",
  "summary": "…unchanged…",
  "adventures": ["goblins-of-greenhollow"],
  "seed_character": { "…": "unchanged, every field" },
  "object_templates": [
    { "id": "mira",        "kind": "creature", "…": "the body of definitions/mira.json, unchanged" },
    { "id": "goblin",      "kind": "creature", "…": "the body of definitions/goblin.json, unchanged" },
    { "id": "goblin-boss", "kind": "creature", "…": "the body of definitions/goblin-boss.json, unchanged" },

    {
      "id": "shepherds-knife",
      "kind": "item",
      "name": "Shepherd's Knife",
      "description": "A short, thin-bladed knife with a horn handle worn smooth by one pair of hands, kept sharp enough to take wool off a hide in a single pull. It was found lying in the grass where the flock was lost, and Mira has kept it behind the bar ever since.",
      "attacks": [
        { "name": "Shepherd's Knife", "to_hit": 4, "damage": "1d4+2" }
      ]
    },
    {
      "id": "bent-horseshoe",
      "kind": "item",
      "name": "Bent Horseshoe",
      "description": "A horseshoe trodden into the mud where the flock was last seen, wrenched out of true by something stronger than a hoof. It is evidence and nothing else, and it sits on the barrel on the green for anyone who wants to look.",
      "attacks": []
    },
    {
      "id": "notched-cleaver",
      "kind": "item",
      "name": "Notched Cleaver",
      "description": "A heavy butcher's cleaver with a chipped edge, its grip rebound in strips of stolen wool. It is Grettle's own, it is the reason the shepherd did not come home, and it goes wherever she goes.",
      "attacks": [
        { "name": "Notched Cleaver", "to_hit": 6, "damage": "2d6+3" }
      ]
    },
    {
      "id": "stolen-fleece",
      "kind": "item",
      "name": "Stolen Fleece",
      "description": "A bundled fleece off one of Greenhollow's missing sheep, still carrying the shear-mark of the household it was taken from. Carried back to the green it is proof of what happened and worth something to the house that lost it.",
      "attacks": []
    },

    {
      "id": "thorn-screen",
      "kind": "fixture",
      "name": "Screen of Thornbrush",
      "description": "A lattice of cut thornbrush dragged across the cave mouth and lashed together at the joints, grey and brittle with age but packed far too thick to push through without tearing skin or making noise.",
      "checks": [
        {
          "action": "Lift the lashed brush aside a branch at a time, without letting it scrape on the stone",
          "dc": 13,
          "success": "A gap wide enough to pass through opens at the edge of the screen, and the goblins on the rocks above hear nothing."
        },
        {
          "action": "Cut through the lashings that hold the screen together",
          "dc": 10,
          "success": "The screen sags open and the cave mouth stands clear; anything watching the entrance sees it happen.",
          "bypassed_by": ["shepherds-knife", "notched-cleaver"]
        }
      ]
    },
    {
      "id": "wool-sack",
      "kind": "fixture",
      "name": "Sack of Stolen Wool",
      "description": "A grain sack hung from a roof beam by its knotted neck, packed round with fleeces that are not the goblins' to keep.",
      "checks": [
        {
          "action": "Work the knotted neck of the sack loose by hand",
          "dc": 8,
          "success": "The sack opens without a sound and the fleeces inside can be lifted out one at a time."
        },
        {
          "action": "Split the sack open with a heavy blade",
          "dc": 12,
          "success": "The sack bursts and the fleeces spill across the floor of the hollow, in full hearing of anything still alive down there.",
          "bypassed_by": ["notched-cleaver"]
        }
      ]
    }
  ]
}
```

**The `"…"` entries above are shorthand for this document only.** The shipped
file carries the real bodies in full; no `…` key exists anywhere in
`backend/content/`.

**Why Grettle's stat block and the `notched-cleaver` template describe the same
weapon, and why that is not duplication to be removed.** A creature's
`stat_block.attacks` is the authority on what *that creature* can do; a carried
item's `attacks` is what the item offers *whoever holds it*, including the
player once she takes it. Nothing sums them, nothing derives one from the other,
and a boss's weapon becoming lootable is precisely the case P1-D22 exists for.
Leave both. The same holds for `shepherds-knife`: it is a weapon in the player's
hand and a bypass token at the thorn screen, and it is one template either way.

### 5.2 `adventures/goblins-of-greenhollow.json`

`id`, `title`, `intro` and `entry_scene` are **unchanged**. The four scenes keep
their ids, their order, their `title`s, their `hidden` entries, their `exits`
and their `pressure`. Two mechanical renames apply throughout, and the prose
changes are exactly the ones printed below — no others.

| Rename | From | To |
|---|---|---|
| Scene key | `"creatures": [...]` | `"placements": [...]` |
| Placement key | `{ "definition": "goblin", ... }` | `{ "template": "goblin", ... }` |

#### `village-green`

`truth` becomes exactly these four entries — the second is reworded and the
third is new; the first and the last are unchanged:

```json
"truth": [
  "Greenhollow is a huddle of a dozen houses around a well and a green, with the Thornway woods a dark line to the north.",
  "Mira, who keeps the village's only inn, has laid a torn grain sack and a bent horseshoe on a barrel on the green — everything that was found near the missing shepherd's flock.",
  "The shepherd's own knife was found lying with them, and Mira has kept it behind the bar since; she means it to go north with whoever goes.",
  "The village has no soldiers and no priest; whoever goes north goes on their own account."
]
```

`npc_intent` becomes exactly:

```json
"npc_intent": "Mira wants the raiding stopped before a third flock disappears and the village starts to starve; she will pay what she can, tell everything she knows and press the shepherd's knife on whoever agrees to go, but she will not go north herself."
```

`consequences`, `hidden` and `exits` are unchanged. `placements`:

```json
"placements": [
  {
    "template": "mira",
    "count": 1,
    "carries": [{ "template": "shepherds-knife", "count": 1 }]
  },
  { "template": "bent-horseshoe", "count": 1 }
]
```

#### `thornway`

**Unchanged in every field**, with the one key rename: `"placements": []`.

#### `lair-maw`

`truth`'s first entry is reworded; the second and third are unchanged:

```json
"A cave mouth opens in the rock, closed off by a screen of dragged thornbrush lashed across it, dead long enough to have gone grey and still packed thick enough to be a wall."
```

`npc_intent`, `consequences`, `hidden` and `exits` are unchanged. `placements`:

```json
"placements": [
  { "template": "goblin", "count": 3 },
  { "template": "thorn-screen", "count": 1 }
]
```

#### `lair-hollow`

`truth`'s first two entries are reworded; the third is unchanged:

```json
"The cave opens into a low hollow lit by a smoking fire, with a shepherd's crook driven upright into the dirt and a grain sack of stolen fleeces hung from the roof beam above the flames.",
"Grettle, the goblin boss, holds this chamber with a single bodyguard goblin at her side, her notched cleaver never out of her hand, and will not be taken by surprise twice."
```

`npc_intent` and `hidden` are unchanged. `consequences`' **second** entry is
reworded; the first is unchanged:

```json
"Killing or driving off both goblins without Grettle escaping ends the raiding on Greenhollow for good, and leaves her cleaver on the floor of the hollow; if she escapes she takes it with her, and the village is safe for now but the raids may begin again wherever she resurfaces."
```

`exits` stays `[]` — this is still the terminal scene. `placements`:

```json
"placements": [
  {
    "template": "goblin-boss",
    "count": 1,
    "carries": [{ "template": "notched-cleaver", "count": 1 }]
  },
  { "template": "goblin", "count": 1 },
  {
    "template": "wool-sack",
    "count": 1,
    "carries": [{ "template": "stolen-fleece", "count": 2 }]
  }
]
```

#### Placements, at a glance

| Scene | `placements` |
|---|---|
| `village-green` | `mira` ×1 carrying `shepherds-knife` ×1; `bent-horseshoe` ×1, no `carries` key |
| `thornway` | `[]` |
| `lair-maw` | `goblin` ×3; `thorn-screen` ×1 |
| `lair-hollow` | `goblin-boss` ×1 carrying `notched-cleaver` ×1; `goblin` ×1; `wool-sack` ×1 carrying `stolen-fleece` ×2 |

Every one of the nine templates is referenced, so R14 is silent:
`shepherds-knife` by a carry **and** by an entry of `thorn-screen`'s
`bypassed_by`; `notched-cleaver` by a carry **and** by an entry of *both*
fixtures' `bypassed_by` lists; `stolen-fleece` by a carry; the rest by
placements.

### 5.3 Deletions

`definitions/mira.json`, `definitions/goblin.json`,
`definitions/goblin-boss.json` and the `definitions/` **directory itself** are
deleted. A rework whose file list carries no deletion is how a stale directory
survives into phase 5.

---

## 6. The service surface delta

Everything in `shared-knowledge.md` §5 holds — synchronous, uncached, module
reference for functions *and* constants (D10), every id argument validated
before a path is built (P1-D18). Two changes:

```python
def load_object_template(
    campaign_id: str, version: str, template_id: str
) -> ObjectTemplate:
    """Raises ContentNotFoundError if the template is not in that campaign
    version; otherwise as load_campaign."""
```

`load_definition` is **renamed, not kept beside it.** No caller exists outside
this module and the test suite, and two names for one lookup is exactly the
second way to do something the repo forbids.

### 6.1 `relative_path`, amended

| Raiser | Condition | `relative_path` |
|---|---|---|
| `list_versions` | the campaign directory does not exist | `campaigns/<campaign_id>` |
| `load_campaign` | the version directory does not exist | `campaigns/<campaign_id>/<version>` |
| `load_scene` | the scene id is not among the campaign's scenes | `campaigns/<campaign_id>/<version>/scene/<scene_id>` |
| `load_object_template` | the template id is not among the campaign's templates | `campaigns/<campaign_id>/<version>/object-template/<template_id>` |

The template row is a **logical address, not a path**: there is no
`object-templates/` directory and no `<id>.json` to name, so the singular
segment and the absent `.json` are deliberate — the same device §6.1 already
uses for `scene/`. The ordering rule is unchanged: in `load_object_template`, a
bad `campaign_id` or `version` raises `load_campaign`'s row; only a bad template
id raises this one.

### 6.2 The tag set

`errors[]` entries keep the grammar
`<path relative to the version directory>: [<TAG>] <detail>` with
`TAG ∈ {READ, SCHEMA, R2 … R18}`. `[R1]` and `[R3]` still never appear.

**Every rule about a template names `campaign.json`**, because that is now the
file an author opens, and puts the template id in the detail. Every rule about a
placement or a carry names the **adventure file** and puts the scene id in the
detail. Examples — the path and the tag are the contract, the detail wording is
free:

```
adventures/goblins-of-greenhollow.json: [R12] scene 'lair-hollow': unknown object template 'notched-cleavor'
adventures/goblins-of-greenhollow.json: [R17] scene 'lair-hollow': carried template 'goblin' is not an item
adventures/goblins-of-greenhollow.json: [R18] scene 'village-green': item placement 'bent-horseshoe' cannot carry
campaign.json: [R12] fixture 'thorn-screen': check 1 bypassed_by names unknown object template 'shepherds-knifr'
campaign.json: [R13] duplicate object template id 'goblin'
campaign.json: [R14] object template 'stolen-fleece' is not referenced by any scene
campaign.json: [R17] fixture 'thorn-screen': check 1 bypassed_by 'goblin' is not an item
campaign.json: [SCHEMA] object_templates.0.creature.stat_block.max_hp: Input should be a valid integer
campaign.json: [SCHEMA] object_templates.7.fixture.checks.1.bypassed_by.1: String should match pattern '^[a-z0-9]+(-[a-z0-9]+)*$'
```

**A `bypassed_by` finding names the fixture template and the offending entry.**
`bypassed_by` is a list, so one check can produce more than one `[R12]` or
`[R17]` entry — one per bad entry, never one collapsed entry for the check. The
path stays `campaign.json` and the tag stays the contract; which entry of which
check the detail names is free wording, but it must be there, because "one of
this fixture's bypass ids is wrong" is not an actionable message.

**The discriminator tag is part of the `loc` path, and no code strips it.**
With `Field(discriminator="kind")`, Pydantic v2 puts the matched tag into the
error location, so the rendered path of a bad field on the first template reads
`object_templates.0.creature.stat_block.max_hp` and a bad field on the eighth
reads `object_templates.7.fixture.checks.0.dc`. A bad **entry of a
`bypassed_by` list** is indexed twice over — `object_templates.7.fixture.checks.1.bypassed_by.0`
is the first listed item id of that fixture's second check. The detail is Pydantic's own
`loc` joined with `.` and its own message — there is no loc-rewriting step to
write, and adding one would be a deviation.

### 6.3 Partial failures

`shared-knowledge.md` §6.3 is unchanged in substance, with "three kinds of file"
reading **two**. The consequence of P1-D24 is that a malformed template is a
`[SCHEMA]` entry on `campaign.json`, located by Pydantic's own `loc`
(`object_templates.<index>.<kind>.…`) — and, because an unusable `campaign.json` is reported
**alone**, a single mistyped template key now suppresses every other finding in
the tree. That cost is accepted: it is the direct consequence of P1-D24's
"fewer kinds of file", the `loc` path points straight at the offending template,
and a tree whose campaign file will not parse has nothing else worth reporting.

---

## 7. The referential rule list — R1 to R18

Applied after every file has passed schema validation. `docs/modules/content.md`
reproduces this table for authors.

| # | Where | Rule | Message names |
|---|---|---|---|
| R1 | load | `campaign.json` exists, is readable and passes schema validation. **Reported as `[READ]` or `[SCHEMA]`, never `[R1]`** | `campaign.json` |
| R2 | load | `campaign.id` equals the campaign directory name | `campaign.json` |
| R3 | **CLI** | The version directory name matches `^v[0-9]+$` | the offending directory |
| R4 | load | Every id in `campaign.adventures` has an `adventures/<id>.json`, with no duplicates in the list. The list is de-duplicated before any later rule is evaluated | `campaign.json` |
| R5 | load | Every `*.json` in `adventures/` is listed in `campaign.adventures` | the orphan adventure file |
| R6 | load | Each adventure's `id` equals its filename stem | the adventure file |
| R7 | load | `adventure.entry_scene` is the `id` of one of that adventure's own scenes | the adventure file |
| R8 | load | A scene `id` appears at most once in the whole campaign | the adventure file holding the **later** occurrence, in `campaign.adventures` order then `scenes` order; the detail names the scene id |
| R9 | load | Every `exit.to` names a scene **in the same adventure**, and never the scene's own id | the adventure file; the detail names the scene id |
| R10 | load | Each adventure has at least one scene with `exits == []` | the adventure file |
| R11 | load | Every scene of an adventure is reachable from `entry_scene` by following exits, ignoring conditions. The entry scene counts as reached | the adventure file |
| R12 | load | **Every object-template reference resolves to a declared template** — `placements[].template`, `carries[].template` and **every entry of every `checks[].bypassed_by` list** alike. An empty `bypassed_by` references nothing and is always silent | the adventure file for a placement or a carry (detail names the scene id); `campaign.json` for a `bypassed_by` entry (detail names the fixture template id and the offending entry) |
| R13 | load | **An object template `id` appears at most once in `campaign.object_templates`.** The first occurrence keeps the id; every later one is reported and excluded from `LoadedCampaign.object_templates`, so it trips no other rule | `campaign.json`; the detail names the id |
| R14 | load | **Every declared object template is referenced at least once** — by a scene `placements[].template`, by a `carries[].template`, or by appearing **anywhere in any `checks[].bypassed_by` list**. Position in the list is irrelevant; one occurrence anywhere is enough. No dead templates | `campaign.json`; the detail names the id |
| R15 | load | An object template `name` is unique across the campaign's templates, compared **case-insensitively** after `ProseText` stripping, **across all three kinds** | `campaign.json`, **every colliding template after the first**, in sorted-id order; the detail names the colliding template id |
| R16 | load | **A template appears at most once in a scene's `placements` list, and at most once in any single placement's `carries` list.** `count` is what expresses "three goblins" | the adventure file; the detail names the scene id and the template id |
| R17 | load | **Every `carries[].template` and every *entry* of every `checks[].bypassed_by` list resolves to a template whose `kind` is `item`.** Each entry is judged on its own, so a list mixing an item and a creature yields one `[R17]` for the creature and nothing for the item | the adventure file for a carry (detail names the scene id); `campaign.json` for a `bypassed_by` entry (detail names the fixture template id and the offending entry) |
| R18 | load | **A placement whose template `kind` is `item` has `carries == []`** | the adventure file; the detail names the scene id and the template id |

**Eighteen rules.** R1–R11 are unchanged from the R1–R16 set. The changes:

| Old | New | What happened |
|---|---|---|
| R12 — `creatures[].definition` resolves to a `definitions/<id>.json` | R12 | **In-memory lookup.** The reference resolves against `campaign.object_templates`, not against the filesystem, and now covers carries and `bypassed_by` too |
| R13 — a definition's `id` equals its filename stem | R13 | **Replaced.** There is no filename, so the file-identity rule becomes an **id-uniqueness within the campaign** rule. It is what makes an id a usable key |
| R14 — every `definitions/*.json` is referenced by a scene | R14 | **Rescoped.** Orphan now means *unreferenced by any placement, any carry and any entry of any `bypassed_by` list*, and it names `campaign.json` rather than a file |
| R15 — `Definition.name` unique | R15 | Substance unchanged; widened to all three kinds |
| R16 — a definition at most once per scene's `creatures` | R16 | Substance unchanged; widened to `carries` lists |
| — | **R17** | New: an item-typed reference must name an `item` |
| — | **R18** | New: an item placement carries nothing |

**Ordering between R12 and R17.** R17 is evaluated only for a reference R12
already resolved — an unknown id yields `[R12]` and nothing else, so one mistake
never produces two findings. This is per **reference**, and an entry of a
`bypassed_by` list is one reference: in `["shepherds-knife", "no-such-thing",
"goblin"]` the second entry yields `[R12]`, the third yields `[R17]`, the first
yields nothing, and that is three independent judgements, not one.

**Identity, amended (P1-D19, as amended by P1-D20 and now by P1-D24).** An
adventure's identity is still its filename stem, and R6's drop semantics are
unchanged: an adventure failing `[R6]`, `[READ]` or `[SCHEMA]` is excluded from
R7–R12 and R16–R18, and its scenes go with it. **A template has no filename, so
its identity is its `id` field, and R13 is what keeps that identity
unambiguous** — the same device R8 uses for scenes. A dropped adventure still
contributes no references to R14, so a template only it referenced is reported
`[R14]`; this remains the deliberate answer, not an oversight.

`seed_character` still has no referential rule: it references nothing (P1-D26).

---

## 8. The `model.md` delta — already applied

Carried instances need somewhere to live at runtime, and `objects` had no owner
reference. **Owner ruling: owned row / parent-child relation, not a blob.** The
edits are already in `docs/general/model.md` and are recorded here so phase 5
inherits the reasoning rather than rediscovering it:

1. **A new subsection, *A carried object is its own row, pointing at its
   owner***: a carried instance is its own `objects` row with a nullable,
   self-referencing `owner_object_id`; `NULL` means the object stands free in
   its scene; the reference cascades with the owner's deletion; one level of
   ownership is all the authored content can express. A carried instance is not
   folded into the owner's inventory blob — it keeps the same identity, the same
   state blob and the same `update_object` path as any other object, which is
   what the one generic table exists to buy.
2. **The promoted columns are nullable and creature-only.** Hit points, maximum
   hit points, armour class and aliveness are populated for `creature` rows
   only; an item and a fixture carry none of them in the authored template
   (§3.6), so there is nothing to promote.
3. **The static-file tree** now shows two kinds of file, `object_templates[]` in
   `campaign.json` and `placements[]` on a scene.

**This step lands no migration and no model**: the `objects` table does not
exist until phase 5. Point 1 is a constraint on phase 5, written down now
because discovering it there is a redesign.

---

## 9. Files this step creates or edits

| File | Owner | Action |
|---|---|---|
| `backend/app/modules/content/schemas.py` | backend-dev | §3 — the union, `FixtureCheck`, `Placement`, `Carried`, the three renamed fields |
| `backend/app/modules/content/service.py` | backend-dev | §6, §7 — templates from `campaign.json`, `load_object_template`, R12–R18 |
| `backend/app/modules/content/README.md` | backend-dev | Update the one-line surface description if it names `Definition` or `load_definition` |
| `backend/app/modules/content/errors.py` | backend-dev | **No change expected.** The error classes are unchanged |
| `backend/app/modules/content/commands.py` | backend-dev | **No change expected.** The CLI contract of `shared-knowledge.md` §7 is untouched |
| `backend/content/campaigns/greenhollow/v1/campaign.json` | backend-dev | §5.1 — `object_templates` appended with nine entries; everything else byte-identical |
| `backend/content/campaigns/greenhollow/v1/adventures/goblins-of-greenhollow.json` | backend-dev | §5.2 — two key renames, the four scenes' placements, and exactly the reworded Story lines §5.2 prints |
| `backend/content/campaigns/greenhollow/v1/definitions/` | backend-dev | §5.3 — three files and the directory **deleted** |
| `docs/modules/content.md` | backend-dev | Reworked to this contract: §4's layout, §3's models and field tables, §7's eighteen rules, §5's worked example, §6.1's locator. The two rules a generator gets wrong by default stay, and a third is added: **a fixture's difficulty is an authored `dc`, never an improvised one** |
| `docs/general/glossary.md` | backend-dev | Strike the parenthetical "(The shipped schema still spells the creature-only ancestor of this entity `Definition`; … and land with the schema change.)" from the *Object template* entry — it has landed |
| `backend/tests/content/**` | qa-backend | The suite, re-authored against this contract |
| `docs/roadmap/Stage-01/phase-01/shared-knowledge.md`, `docs/general/model.md`, `docs/roadmap/Stage-01/phase-01/steps.md` | architect | **Already applied in this pass.** No dev agent edits them |

**qa-backend never writes into `backend/content/` or `backend/app/`;
backend-dev never writes into `backend/tests/`.** The phase's central evidence is
circular otherwise.

---

## 10. Acceptance criteria

Numbered, each provable or refutable without reading the implementation.

### The schema

1. A `campaign.json` whose `object_templates` holds a `creature` entry with
   `id`, `kind`, `name`, `description`, `disposition` and `stat_block` loads,
   and the loaded object is a `CreatureTemplate` whose `kind` is `"creature"`.
2. An `item` entry with `id`, `kind`, `name`, `description` and `attacks` loads
   as an `ItemTemplate`; an `item` entry that omits `attacks` loads with
   `attacks == []`.
3. A `fixture` entry with `checks` holding one `{action, dc, success}` loads as a
   `FixtureTemplate`, and that check's `bypassed_by` is `[]` when the key is
   absent. An explicit `"bypassed_by": []` loads to the same value.
3a. **`bypassed_by` is a list, and only a list.** A check with
   `"bypassed_by": ["shepherds-knife", "notched-cleaver"]` loads with
   `bypassed_by == ["shepherds-knife", "notched-cleaver"]`, in that order, and a
   check with `"bypassed_by": ["shepherds-knife"]` loads with a one-element
   list. Each of these fails `[SCHEMA]`: `"bypassed_by": "shepherds-knife"` (a
   bare string, the old scalar form); `"bypassed_by": null`; and
   `"bypassed_by": ["Shepherds Knife"]` (an entry that is not a `ContentId`).
4. Each of these fails with a `[SCHEMA]` entry on `campaign.json`: an `item`
   entry carrying `stat_block`; an `item` entry carrying `disposition`; a
   `creature` entry carrying `checks`; a `fixture` entry carrying `attacks`; a
   `creature` entry carrying `attacks` at the template's top level (they belong
   inside `stat_block`).
5. A template entry with no `kind`, and one with `"kind": "creatures"`, each
   fail with a `[SCHEMA]` entry on `campaign.json`.
6. A `fixture` entry with `"checks": []`, and one with no `checks` key, each
   fail `[SCHEMA]`.
7. A `FixtureCheck` with `dc` of `0` and one with `dc` of `31` each fail
   `[SCHEMA]`; `1` and `30` are accepted.
8. A `Carried` entry carrying a `carries` key of its own fails `[SCHEMA]` —
   carrying is not recursive.
9. A `Placement` with `"count": 0` fails `[SCHEMA]`; a `Placement` with no
   `count` loads with `count == 1` and `carries == []`.
10. A scene using the old key `"creatures"` fails `[SCHEMA]`, and a placement
    using the old key `"definition"` fails `[SCHEMA]`. There is no compatibility
    alias.
11. `Campaign` with `"object_templates": []` fails `[SCHEMA]`.
12. `SeedCharacter` is unchanged: a `campaign.json` whose `seed_character`
    carries `inventory` as a list of strings loads, and no item-template
    reference is required or accepted there.

### The rules

13. A placement naming an undeclared template id produces exactly one entry,
    tagged `[R12]`, on the adventure file, with the scene id in the detail — and
    **no** `[R17]` entry for the same reference.
14. A `carries[].template` naming an undeclared id produces one `[R12]` entry on
    the adventure file; a `checks[].bypassed_by` **entry** naming an undeclared
    id produces one `[R12]` entry on `campaign.json` naming the fixture template.
14a. **Per entry, not per check.** A `bypassed_by` list holding two undeclared
    ids produces **two** `[R12]` entries; a list holding one declared item id and
    one undeclared id produces exactly **one** `[R12]`; an empty `bypassed_by`
    produces none.
15. Two templates sharing an `id` produce one `[R13]` entry on `campaign.json`
    naming that id, and the *first* of the two is the one present in
    `LoadedCampaign.object_templates` — the duplicate produces no `[R15]`.
16. A declared template referenced by no placement, no carry and by no entry of
    any `bypassed_by` list produces one `[R14]` entry on `campaign.json`. A
    template referenced **only** by a `carries[]` entry produces none; a template
    referenced **only** as the **first** entry of some `bypassed_by` list
    produces none; and a template referenced **only** as a **later** entry of
    some `bypassed_by` list produces none either.
17. Two templates whose `name` differs only in case produce one `[R15]` entry on
    `campaign.json` naming the later of the two in sorted-id order — including
    when the two are of different kinds.
18. The same template id twice in one scene's `placements` produces one `[R16]`
    entry; the same template id twice in one placement's `carries` produces one
    `[R16]` entry; the same template id once in `placements` and once inside a
    `carries` in the same scene produces **none**.
19. A `carries[].template` that resolves to a `creature` or a `fixture` template
    produces one `[R17]` entry on the adventure file; a `checks[].bypassed_by`
    **entry** that resolves to a non-`item` template produces one `[R17]` entry
    on `campaign.json`.
19a. **Each entry judged alone.** A `bypassed_by` list holding one `item` id and
    one `creature` id produces exactly one `[R17]`, and the `item` entry produces
    no finding of any kind; a list holding two non-`item` ids produces two
    `[R17]` entries.
20. A placement whose template is an `item` and whose `carries` is non-empty
    produces one `[R18]` entry on the adventure file. A `creature` placement and
    a `fixture` placement with non-empty `carries` each produce **none**.
21. `ContentInvalidError.errors` is sorted, and every entry matches
    `^[^:]+(/[^:]+)*: \[(READ|SCHEMA|R([2-9]|1[0-8]))\] `. No entry is tagged
    `[R1]` or `[R3]`.
22. A tree that is valid under every rule loads with an **empty** problem set —
    i.e. none of the eighteen rules fires on the worked example of §5.

### The service

23. `service.load_object_template("greenhollow", "v1", "wool-sack")` returns a
    `FixtureTemplate`, and `service.load_definition` no longer exists on the
    module.
24. `service.load_object_template("greenhollow", "v1", "no-such-thing")` raises
    `ContentNotFoundError` whose `relative_path` is
    `campaigns/greenhollow/v1/object-template/no-such-thing`.
25. `service.load_object_template("greenhollow", "v1", "../campaign")` raises
    `ContentNotFoundError` and opens no file; `service.load_object_template("../../app",
    "v1", "mira")` raises with `relative_path` `campaigns/../../app/v1`.

### The shipped tree

26. `backend/content/campaigns/greenhollow/v1/definitions/` **does not exist**,
    and the version directory contains exactly `campaign.json` and
    `adventures/`.
27. `campaign.json`'s `object_templates` has exactly nine entries, in this
    order: `mira`, `goblin`, `goblin-boss` (`kind` `creature`);
    `shepherds-knife`, `bent-horseshoe`, `notched-cleaver`, `stolen-fleece`
    (`kind` `item`); `thorn-screen`, `wool-sack` (`kind` `fixture`).
27a. **Completeness — no mechanism ships unexercised.** Every row of §5.0's
    table holds of the shipped tree, each checkable on its own: a creature
    placement that carries (`village-green`/`mira`, `lair-hollow`/`goblin-boss`);
    a fixture placement that carries (`lair-hollow`/`wool-sack`); a bare item
    placement with no `carries` key (`village-green`/`bent-horseshoe`); a carry
    with `count > 1` (`stolen-fleece`, 2); a placement with `count > 1`
    (`lair-maw`/`goblin`, 3); a scene with `placements == []` (`thornway`); an
    item template with non-empty `attacks` and one with `attacks == []`; on each
    fixture, a first `checks[]` entry with **no** `bypassed_by` key, loading as
    `[]`; and, on each fixture, a second entry whose `bypassed_by` lists only
    `item` templates, at least one of which is itself placed or carried somewhere
    in the tree — `thorn-screen` → `shepherds-knife`, carried by `mira` in
    `village-green`; `wool-sack` → `notched-cleaver`, carried by `goblin-boss` in
    `lair-hollow`.
27b. **Both `bypassed_by` cardinalities ship.** `thorn-screen`'s second check has
    `bypassed_by == ["shepherds-knife", "notched-cleaver"]` — two entries, in
    that order — and `wool-sack`'s second check has
    `bypassed_by == ["notched-cleaver"]` — exactly one. Both fixtures' first
    checks have `bypassed_by == []`, and the `bypassed_by` key is absent from
    both of them in the shipped JSON.
28. **Fidelity — what did *not* change.** `campaign.json`'s `id`, `title`,
    `summary`, `adventures` and the whole of `seed_character` are byte-identical
    to their pre-rework values; each of the three creature templates is
    byte-identical to the body of the `definitions/<id>.json` it came from,
    except for the added `"kind": "creature"`; and the adventure file's `id`,
    `title`, `intro`, `entry_scene`, every scene `id` and `title`, every
    `hidden` entry, every `exits` entry and every `pressure` value are
    unchanged. Provable against `git show` of the pre-rework files.
28a. **Fidelity — what did change.** Every `truth`, `npc_intent` and
    `consequences` value in the adventure file is either byte-identical to its
    pre-rework value or **character-for-character equal to the replacement §5.2
    prints**. No third case exists: no line of Story in the shipped tree is
    absent from both the pre-rework file and §5.2.
29. **Migration fidelity — keys.** No `"creatures"` key and no `"definition"`
    key remains anywhere under `backend/content/`.
30. `village-green` places `mira` carrying `shepherds-knife` × 1 and
    `bent-horseshoe` with no `carries` key; `lair-maw` places `goblin` × 3 and
    `thorn-screen` × 1; `lair-hollow`'s `goblin-boss` placement carries
    `notched-cleaver` × 1 and its `wool-sack` placement carries `stolen-fleece`
    × 2; `thornway`'s `placements` is `[]`. The four scene ids, their order and
    their exits are unchanged.
31. Every criterion of step 1.3 that survives the rename still holds of the
    shipped tree: one campaign, one version `v1`, one adventure, four scenes, a
    terminal scene that is not the entry scene, every scene reachable, `goblin`
    placed in two scenes, a creature template with `attacks: []` (`mira`) and
    ones with a non-empty `attacks`, two `hidden` entries across two scenes, one
    exit with a `condition` and one without, a placement with `count > 1`, and a
    `consequences` entry naming the villain verbatim.

### The command line

32. `app content validate`, run in the repository as checked out, exits **`0`**,
    writes `greenhollow/v1: ok` to stdout (compared after `.strip()`) and
    **nothing** to stderr.

### The suite and the guide

33. The whole backend suite passes: `make backend-test` is green.
34. `docs/modules/content.md` documents every model and every field of §3, every
    rejecting constraint, all eighteen rules with their tags, and reproduces §5's
    worked example; it contains no reference to `Definition`, `definitions/`,
    `creatures[]` as a scene key or `load_definition`.
35. No file under `backend/` or `docs/` (outside `docs/roadmap/`, where history
    is allowed to name it) treats `definitions/` as a live path — i.e. no code
    builds or opens one, and no doc describes one as part of the current
    layout. A sentence stating the directory no longer exists is not a
    violation; a substring grep for the literal text `definitions/` is not the
    right check, since the two-file layout's own documentation must say so.
    Separately, `docs/general/glossary.md` no longer carries the "still spells
    … `Definition`" parenthetical.

---

## 11. Static checks the dev agent runs

```bash
cp .env.dist .env                      # once, if not already done
cd backend && uv run ruff check . && uv run ruff format --check .
docker compose run --rm --no-deps app-cli app content validate; echo "exit=$?"
```

Expected: ruff clean; exit `0`, stdout exactly `greenhollow/v1: ok`, stderr
empty.

Also verify by hand before handing over:

- Every file under `backend/content/` parses as JSON.
- `git status --porcelain -- backend/content/` shows **two modified files and
  three deletions**, and nothing else;
  `backend/content/campaigns/greenhollow/v1/definitions/` is gone.
- `git diff -- backend/content/` reads as a move plus two key renames plus the
  additions of §5: every `-` line of a deleted definition file reappears inside
  `object_templates`, with `"kind": "creature"` its only difference, and every
  changed Story line's `+` side is character-for-character what §5.2 prints.

**Do not run pytest** — the suite belongs to qa-backend. No Alembic round-trip:
no migration.

---

## 12. The parallelisation split

**This step is backend-only.** The content module has no HTTP route, no wire
schema, no frontend file and no i18n key, and this rework adds none — so
**frontend-dev, qa-frontend and ux-designer are not dispatched this loop, and
there is nothing for them to do.** That is the split: there is no second tree.

Within the backend, the step is sequential inside itself, because the evidence
depends on the artefact:

| Agent | Owns | When |
|---|---|---|
| qa-backend (mode A) | `backend/tests/content/**` — the suite re-authored from this spec alone, expected to fail | First, in parallel with nothing else it can collide with |
| backend-dev | `backend/app/modules/content/**`, `backend/content/campaigns/greenhollow/v1/**`, `docs/modules/content.md`, `docs/general/glossary.md` | First, concurrently with qa-backend's authoring. Runs §11's checks |
| qa-backend (mode B) | Running the suite and returning a verdict per numbered criterion | After backend-dev lands |

qa-backend can author every criterion of §10 before the implementation exists:
the ids, the tags, the paths, the `relative_path` strings, the shipped tree's
nine template ids and §5.0's completeness table are all pinned above.

**The owner is in the loop once**, on this spec, for all of §5's prose — the six
new templates of §5.1 and the reworded Story lines of §5.2. Once the spec is
approved that acceptance is spent, and no agent is to write, improve or reword
Greenhollow prose during implementation.

---

## 13. Deviation clause

**Zero deviations from this spec.** In particular: do not add a field to any
template, do not give an item or a fixture hit points or an armour class, do not
make carrying recursive, do not make `bypassed_by` optional, nullable or scalar
again, do not accept a bare string there "for convenience", do not infer a
bypass from an item's name, description or `attacks`, do not keep a `definition` alias for one release, do not
convert `SeedCharacter.inventory`, do not add a nineteenth rule, and **write no
Greenhollow prose that §5 does not print.** §5's prose is the whole of the
licence: everything it marks unchanged stays byte-identical, everything it
prints is copied character for character, and ids, numbers and scene order are
fixed either way.

If something here cannot be implemented as written — if a rule is ambiguous, if
two rules overlap on one input, if the union will not discriminate as described,
or if the migrated tree will not validate for a reason this spec does not
explain — **stop and report it**. That is a finding about the contract, and
surfacing it is worth more than a repair nobody agreed to.
