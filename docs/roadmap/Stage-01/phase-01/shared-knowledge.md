---
title: "Phase 1 — Adventure Content — shared knowledge"
stage: 1
phase: 1
created: 2026-09-11
revised: 2026-09-11
---

# Phase 1 — Adventure Content — shared knowledge

Binding contract for every agent working in phase 1. Read this before any step
file. Where this document and an agent report disagree, this document wins;
where this document and the code disagree, the code wins and this document is
corrected.

Phase 0's [`shared-knowledge.md`](../../phase-0/shared-knowledge.md)
`## Landed decisions` **D1–D38 remain in force**. D1 (modular layout and the
placement bar), D8 (transactions belong to services), D9 (the engine is never
built at import time), D10 (service signatures are contract), D23
(dev dependencies live in `[dependency-groups] dev`), D31 and D36 (the
`filterwarnings = ["error"]` traps) and D38 (ULIDs) all bind here.

The stage contract is [`../README.md`](../README.md) — its §1 capability
inventory, §2 dependency graph, §3 parallelism, §5 scope fence, §7
open-decisions register and §9 doc-correction register bind this phase. The
step cut is [`steps.md`](steps.md).

## What this phase delivers

A `content` backend module that reads hand-authored, version-pinned campaign
JSON from `backend/content/`, validates it against a pinned Pydantic schema and
a fixed list of referential rules, and exposes it to later phases as typed
Python objects; a Typer command `app content validate` that proves a content
tree correct from the command line; a schema-documentation artefact at
`docs/modules/content.md` complete enough that an agent could author a
conformant campaign from it alone; and one authored campaign — one adventure,
at least three scenes, campaign-scoped definitions and a seed player character
— that passes both. **Phase 1 lands no HTTP route, no database table, no
migration, no frontend file, no i18n key and no new environment variable.** Its
evidence is the CLI and the backend test suite.

Its consumers are phase 5 (pins a content version on a run and eagerly
instantiates every creature the pinned content declares), phase 7 (offers the
campaign and its prose when a run starts) and phase 8 (the DM's scene and
definition tool bindings).

---

## 1. Module layout and file ownership

One new backend module, `content`, plus one additive block in `app/cli.py`.

| Path | Owner | Step | Contents |
|---|---|---|---|
| `backend/app/modules/content/__init__.py` | backend-dev | 1.1 | Empty, as every other module's is. |
| `backend/app/modules/content/schemas.py` | backend-dev | 1.1 | Every Pydantic content model of §3. No wire schemas — see P1-D2. |
| `backend/app/modules/content/errors.py` | backend-dev | 1.1 | `ContentError`, `ContentNotFoundError`, `ContentInvalidError` (§6). |
| `backend/app/modules/content/service.py` | backend-dev | 1.1 | `CONTENT_ROOT`, `VERSION_PATTERN` and every exported loader/validator function of §5. All synchronous. |
| `backend/app/modules/content/commands.py` | backend-dev | 1.1 | `content_app: typer.Typer` and the `validate` command (§7). |
| `backend/app/modules/content/README.md` | backend-dev | 1.1 | Module intent / owns / surface / notes, in the shape of `backend/app/modules/users/README.md`. Links to `docs/modules/content.md` for the field reference rather than repeating it. |
| `backend/app/cli.py` | backend-dev | 1.1 | **Two added lines only** (§7.2). No other edit. |
| `docs/modules/content.md` | backend-dev | 1.2 | The authoring guide / schema reference (§9.1). |
| `docs/README.md` | backend-dev | 1.2 | One added table row under *Modules* (§9.2). |
| `docs/general/model.md`, `docs/general/architecture.md`, `docs/general/requirement-map.md` | backend-dev | 1.2 | The corrections of §9.2. |
| `docs/roadmap/Stage-01/README.md` | backend-dev | 1.2 | Three added rows: two in §9's doc-correction register, one in §7's open-decisions register (§9.3). The only edit phase 1 makes to another plan document. |
| `backend/content/campaigns/**` | backend-dev | 1.3 | The authored content tree (§4), written **from `docs/modules/content.md`**, not from the implementation. **In the P1-D20 rework this is a mechanical migration of the already-authored tree, with no authoring and no prose change — see `step-1.3.md` §3.** |
| `backend/tests/content/**` | qa-backend | 1.1, 1.3 | The test suite, mirroring the module one-to-one (§8). |

**qa-backend never writes into `backend/content/`.** If the agent that proves
the shipped tree valid is also the agent that authored it, the phase's central
evidence is circular. Symmetrically, backend-dev never writes into
`backend/tests/`.

*Human in the loop* for step 1.3 means an agent authors the campaign and the
**owner reads the prose and accepts or rejects the diff**; no agent judges prose
quality. **This was satisfied in the first pass and does not recur in the
P1-D20 rework**, which moves already-accepted prose between files without
changing a character of it: `step-1.3.md` §3 and §9 close the owner out of that
pass, and its criterion 24 — byte-identical scene bodies — is what stands in for
the acceptance.

There is **no** `models.py` (no table) and **no** `routes.py` (no route) in this
module. Do not create empty ones.

---

## 2. Where content lives and how the path is resolved

Content lives at **`backend/content/`**, not at the repository root.

```python
# backend/app/modules/content/service.py
from pathlib import Path

# backend/app/modules/content/service.py -> parents[3] == backend/
CONTENT_ROOT: Path = Path(__file__).resolve().parents[3] / "content"
```

Why this location and this resolution, verified against the infrastructure:

- `docker/backend.Dockerfile` runs `COPY backend/ ./` into `WORKDIR /app`, so
  `backend/content/` is present in the image at `/app/content` with no
  `COPY` line to add.
- `compose.yaml` bind-mounts `./backend:/app` for both `app-web` and `app-cli`,
  so the same path is the live host tree in development.
- `.dockerignore` excludes `docs` but nothing under `backend/`.
- On the host, `uv run pytest` from `backend/` sees the identical relative
  path.

A repository-root `content/` would need a Dockerfile `COPY`, two compose mounts
and a settings field whose value differs between the container and a host run.
`backend/content/` needs none of that: **zero configuration, no environment
variable, no `Settings` field.** Never read `os.environ` for a content path.

`CONTENT_ROOT` is read **inside function bodies**, never captured as a default
argument value, so `monkeypatch.setattr(service, "CONTENT_ROOT", tmp_path)`
works (§8). `commands.py` obeys the same rule through the module reference
(§7.2).

---

## 3. The content schema

### 3.0 Conventions binding every model

```python
# backend/app/modules/content/schemas.py
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class ContentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


ContentId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
ProseText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
```

- **JSON keys are `snake_case` and identical to the Python field names.** No
  alias generator, no `alias=`. `CamelModel` in `app/core/schemas.py` exists for
  **the wire**; content files are not the wire — nothing here is ever serialised
  to a client, and phases 5/7/8 build their own `CamelModel` responses from
  these objects. A 1:1 mapping between `docs/modules/content.md`, the JSON key
  and the Python attribute removes a whole class of authoring mistake.
- **`extra="forbid"`** — a mistyped key is a loud load error, not silence. This
  is the single most valuable property of the schema for a hand- or
  agent-authored tree.
- **`frozen=True`** — content is read-only at runtime (`model.md`). Note it is
  **shallow**: the `list` and `dict` values inside a frozen model are ordinary
  mutable containers, so "read-only" is a convention for callers, not a
  guarantee the type system enforces.
- **Every id field is `ContentId`**: lowercase kebab-case. Ids appear in file
  paths and, in phase 5, in deterministic object instance keys.
- **Every human-readable string field is `ProseText`**, which strips surrounding
  whitespace and then requires at least one character — so `" "` is rejected
  rather than accepted as content. One alias, used everywhere; never
  `Field(min_length=1)` on a `str`.
- **British spelling where the glossary pins a term.** `docs/general/glossary.md`
  says terms are "used exactly as defined here — in code, in content and in the
  UI", and it defines *Armour Class*. The field is therefore `armour_class`,
  not `armor_class`.
- **No optional field exists without a named Stage-01 consumer.** Each field
  below names one.
- **No string and no list has an upper bound.** Nothing in this phase truncates
  or rejects for size, so a scene with two hundred `truth` entries loads
  happily; phase 8's prompt composer inherits the whole of that problem and
  owns any budget (§10.5).

### 3.1 `Abilities`

The six 5e ability scores. Consumers: phase 8's checks and saves — the DM needs
a modifier it did not invent — and phase 7's character sheet display.
Stage-01 resolves every check on the **raw ability modifier** derived from these
six numbers; proficiency is not modelled (§10.4).

```python
class Abilities(ContentModel):
    strength: int = Field(ge=1, le=30)
    dexterity: int = Field(ge=1, le=30)
    constitution: int = Field(ge=1, le=30)
    intelligence: int = Field(ge=1, le=30)
    wisdom: int = Field(ge=1, le=30)
    charisma: int = Field(ge=1, le=30)
```

All six required. A partial ability set is not a thing in 5e.

### 3.2 `Attack`

```python
class Attack(ContentModel):
    name: ProseText
    to_hit: int                                  # the bonus added to the d20
    damage: ProseText                            # a dice expression, e.g. "1d6+2"
```

`to_hit` is the **complete** bonus already baked in by the author — phase 1
carries no proficiency bonus and no level to derive one from (§10.4).
`damage` is passed verbatim to phase 3's dice parser through phase 8's
`roll_dice` binding; phase 1 does **not** validate the expression, because
phase 3's parser is the single authority on that grammar and does not exist yet
(§10.1).

### 3.3 `StatBlock`

Carried by **every** definition (§3.4). Consumers: phase 5's eager object
instantiation, which promotes HP, max HP, AC and aliveness to real columns, and
phase 8's creature tool binding.

```python
class StatBlock(ContentModel):
    max_hp: int = Field(ge=1)
    armour_class: int = Field(ge=1)
    abilities: Abilities
    attacks: list[Attack] = Field(default_factory=list)
    traits: list[ProseText] = Field(default_factory=list)   # prose special abilities
```

`max_hp` and `armour_class` are exactly the two promoted columns phase 5 needs;
current HP starts equal to `max_hp` and aliveness starts true, so content
carries neither. `traits` feeds the DM prompt only.

**`attacks: []` is what "cannot fight" means.** The innkeeper has hit points, an
armour class and no attacks — the same shape as the goblin, with one list empty.
There is no optional branch anywhere in the schema for a non-combatant.

Deliberately **not** present: speed (no map), challenge rating (the DM does not
balance encounters at runtime), level, proficiency bonus, skills and saves
(§10.4).

### 3.4 `Definition`

One entity for NPCs and monsters alike — `model.md` rules that "a monster *is*
an NPC" and that there is no npc/monster split. Campaign-scoped (`model.md`:
the villain of adventure 1 returns in adventure 3). File:
`definitions/<id>.json` — **the one thing in the tree that is neither campaign
metadata nor an adventure, because it belongs to no single adventure.**

**Why the word is `Definition` and not `npc` or `creature` (P1-D21).** A
definition is a **template**: the campaign-scoped description of a kind of
creature. The thing that exists in a scene during a run is an **instance** of
it — a creature object with current hit points, an aliveness flag and a
disposition blob, created by phase 5. The two are different objects with
different lifetimes, and *creature* is already the instance's word, so using it
for both would put a homonym at exactly the seam where phase 5 and phase 8 have
to tell them apart. `npcs/` names one of the two populations the entity covers
and reopens the question P1-D3 closes. `docs/general/glossary.md` already
defines *Definition* in these terms and its terms bind code, content and UI.

```python
class Definition(ContentModel):
    id: ContentId
    name: ProseText                              # player-facing; unique within the campaign (R15)
    description: ProseText                       # who they are, what they look like
    disposition: ProseText                       # what they want, how they treat the player
    stat_block: StatBlock                        # required — every creature has HP and AC
```

`name` is what the player sees and what phase 5 writes onto the instantiated
object; `description` and `disposition` are DM-prompt material; `disposition`
also seeds the object state blob's disposition (`model.md`).

`stat_block` is **required**. A definition placed in a scene becomes an object
row in phase 5, whose HP, max HP and AC are promoted columns — an optional stat
block would leave phase 5 inventing them, which is exactly what the mechanics
layer must never do.

### 3.5 `Secret`

One entry of a scene's `hidden` list.

```python
class Secret(ContentModel):
    fact: ProseText                              # what is true but not apparent
    dc: int = Field(ge=1, le=30)                 # the target number to discover it
    discovered_by: ProseText                     # prose: the ability/skill and the action
```

`dc` exists so the DM has a target number it did not invent — "the dice are
real" (app-vision) requires an authored DC for authored secrets. `discovered_by`
is prose (e.g. `"a Wisdom (Perception) check on entering, or searching the
crates"`) rather than a skill enum, because encoding the 5e skill list into
content duplicates SRD text the RAG corpus already holds.

`hidden` and `dc` must never reach the player — see §10.3, which binds phase 8.

### 3.6 `CreaturePlacement`

```python
class CreaturePlacement(ContentModel):
    definition: ContentId                        # -> definitions/<id>.json
    count: int = Field(default=1, ge=1)
```

`count` is what makes phase 5's eager instantiation possible without invention:
it says how many object rows to create, and lets phase 5 derive a deterministic
instance key per placement. One placement list covers named NPCs (`count: 1`)
and monster groups alike, mirroring the one-`Definition` decision.

**A definition appears at most once in a scene's `creatures` list** (R16). Two
entries for the same definition would make phase 5's instance key depend on list
position, turning an authoring convenience into an ordering contract; `count` is
what expresses "three goblins".

### 3.7 `Exit`

```python
class Exit(ContentModel):
    to: ContentId                                # a scene id in the same adventure
    description: ProseText                       # what the player perceives as the way on
    condition: ProseText | None = None           # prose the agent judges; null = always open
```

**This is a list, not the object map `model.md` sketches as `exits{}`.** A map
keyed by direction implies a map the game does not have; a map keyed by target
scene id duplicates the value and forbids two distinct routes to the same place.
A list of objects is the shape that actually carries `description` and
`condition`. Recorded as a doc correction (§9.2).

**How a non-deterministic exit condition is expressed:** as prose in
`condition`, and only as prose. `model.md` rules that situational facts have no
flag store, so there is no flag to reference and no machine-evaluable condition
language. The DM judges `condition` against scene `truth`, the journal and what
has happened — e.g. `"the warden has been convinced, or the bar has been
broken"`. A condition **must never** name a variable, a flag or a comparison;
`docs/modules/content.md` says so in those words.

**A scene with `exits: []` is terminal** — reaching it ends the adventure. That
is the only way an adventure ends, and every adventure must contain at least one
(R10).

### 3.8 `Scene`

**A scene is not a file.** It is an element of its adventure's `scenes` list
(§3.9), so a scene physically belongs to exactly one adventure and cannot be
orphaned or shared. It keeps its `id`, which is how exits, runs and
`LoadedCampaign.scenes` address it. Facts, intentions and consequences — never a
script.

```python
class Scene(ContentModel):
    id: ContentId
    title: ProseText                             # short location label
    truth: list[ProseText] = Field(min_length=1) # what is true here
    npc_intent: ProseText | None = None          # what the creatures present want
    consequences: list[ProseText] = Field(default_factory=list)
    hidden: list[Secret] = Field(default_factory=list)
    creatures: list[CreaturePlacement] = Field(default_factory=list)
    exits: list[Exit] = Field(default_factory=list)
    pressure: ProseText | None = None            # what forces the scene forward
```

Consumers: `title` — phase 9's location display and the DM prompt; `truth` —
the DM prompt (required, at least one fact, or the scene says nothing);
`npc_intent` — the DM prompt, null in a scene with no creatures; `consequences`
— the DM prompt, *what follows from plausible player action*, never *what the
player does*; `hidden` — the DM prompt and its checks; `creatures` — phase 5's
eager instantiation and phase 8's scene tool; `exits` — phase 5's scene advance;
`pressure` — the DM prompt.

`model.md`'s sketch merged `npcs[]` and `monsters[]`; they are one
`creatures[]` here, per §3.4. Recorded as a doc correction (§9.2).

### 3.9 `Adventure`

File: `adventures/<id>.json` — **the whole adventure, its scenes included**
(P1-D20).

```python
class Adventure(ContentModel):
    id: ContentId
    title: ProseText                             # player-facing
    intro: ProseText                             # prose read when the adventure starts
    entry_scene: ContentId                       # must be the id of a scene below
    scenes: list[Scene] = Field(min_length=1)    # the scenes themselves, inline
```

`intro` is mandated by `model.md`'s correction and is consumed by phase 8's
opening narration and phase 9's display.

`scenes` carries **`Scene` objects, not ids**. Containment is the model: a scene
belongs to one adventure and to no other, so the file layout states that
directly instead of asserting it through a rule. Its order is authoring
convenience and carries no meaning, because traversal is defined by exits and by
`entry_scene`.

### 3.10 `SeedCharacter`

The starting player character, carried inline in `campaign.json`. Stage README
§9 pins its role: **a fixture, so phase 5 has a character before phase 7's
generation agent exists** — it is not a player-facing "skip character creation"
option (stage README §5 fences that out). Its fields are exactly what phase 5
writes into the player's creature object.

```python
class SeedCharacter(ContentModel):
    name: ProseText
    race: ProseText
    character_class: ProseText
    background: ProseText                        # prose, one or two sentences
    appearance: ProseText                        # prose; DM narration material
    abilities: Abilities
    max_hp: int = Field(ge=1)
    armour_class: int = Field(ge=1)
    inventory: list[ProseText] = Field(default_factory=list)
```

The JSON key is `character_class`, **not** `class`: `class` is a Python keyword,
and one aliased field is not worth introducing a second naming mechanism into a
schema whose whole value is that the JSON key and the Python attribute are the
same string. `extra="forbid"` makes the mistake loud.

No `portrait` field: phase 7 owns portraits and ships a deterministic
placeholder. No `level`, no proficiency, no authored attacks (§10.4). The seed
character references nothing else in content — that is deliberate, and it is why
there is no referential rule for it.

### 3.11 `Campaign`

File: `campaign.json`.

```python
class Campaign(ContentModel):
    id: ContentId                                # equals the campaign directory name
    title: ProseText                             # player-facing
    summary: ProseText                           # the pitch, shown when a run starts
    adventures: list[ContentId] = Field(min_length=1)   # ordered
    seed_character: SeedCharacter
```

`adventures` **is** ordered — it is the play order, and phase 5 reads it to know
which adventure follows which. There is no `version` field: the version is the
directory name and nothing else, so the two can never disagree.

### 3.12 `LoadedCampaign`

The return type of a full load. Not a file — an in-memory aggregate.

```python
class LoadedCampaign(ContentModel):
    campaign: Campaign
    version: str
    adventures: dict[str, Adventure]     # keyed by id, in campaign.adventures order
    scenes: dict[str, Scene]             # every scene of every adventure, flattened
    definitions: dict[str, Definition]   # every definition in the campaign
```

`scenes` is **flat across adventures** and is keyed by scene id, which R8 makes
unique across the whole campaign — so a run that pins a scene id needs no
adventure id beside it, and this aggregate is unchanged by P1-D20. The file
layout is an authoring concern and stops at the loader.

Consumer: phase 5 walks `scenes.values()` for `creatures` placements and
`definitions` for stat blocks, which is precisely "instantiate every object the
pinned content declares, across all adventures", and reads `version` back rather
than trusting what it asked for.

Because R15 makes `Definition.name` unique within a campaign, **a lookup by
display name over `definitions.values()` is well defined** — it returns at most
one definition. That is the content-side precondition phase 8 needs if it keeps
a name-addressed creature tool; the tool's own name and argument remain phase
8's to pin (§10.6).

---

## 4. The content tree

```
backend/content/
└── campaigns/
    └── <campaign_id>/
        └── <version>/
            ├── campaign.json                      # metadata + the seed player character
            ├── adventures/<adventure_id>.json     # the adventure *and its scenes*
            └── definitions/<definition_id>.json   # campaign-scoped, shared between adventures
```

**Three kinds of file, and the granularity of each follows its scope** (P1-D20).
A scene belongs to exactly one adventure, so it lives inside that adventure's
file. A definition is campaign-scoped by P1-D3 — the villain of adventure 1
returns in adventure 3 — so it cannot live inside an adventure and stays its own
file. The campaign's own metadata and its seed character are neither, and stay
in `campaign.json`.

**Only `*.json` files are considered.** A `README.md`, a `.DS_Store` or an
editor swap file inside `adventures/` or `definitions/` is ignored entirely — it
is never read and never reported as an orphan.

**A missing `adventures/` or `definitions/` directory is an empty directory, not
an exception.** The loader globs (`(base / "adventures").glob("*.json")`, which
yields nothing for a path that does not exist) rather than iterating, so the
absence surfaces as the referential failure it actually is — R4 reporting an
adventure that cannot be found — instead of an `OSError`.

**Versioning.** A version is a directory named `v<n>` — `VERSION_PATTERN =
re.compile(r"^v[0-9]+$")`, e.g. `v1`, `v2`. A loader is always given a campaign
id *and* a version and serves exactly that directory; it never guesses and never
merges. Content is extended by copying the tree to `v2` and editing there, never
by editing a published version in place, which is what makes a run pinned to
`v1` reproducible forever. This is the whole versioning mechanism — no manifest,
no semver, no `published` flag, because a directory name already expresses
everything the requirement needs.

`backend/content/srd/` belongs to phase 4. Phase 1 creates `campaigns/` only.

### 4.1 A complete worked example

This is a minimal campaign that is valid against **every** rule in §11. It is
the contract artefact backend-dev and qa-backend share: field names, casing and
nesting are normative here, and `docs/modules/content.md` reproduces it. It is
**three files** — the whole adventure, both its scenes included, is one of
them.

**It is illustrative only and is never committed to `backend/content/`.** The
shipped campaign is `greenhollow/v1`, authored in step 1.3; `hollow-reach` exists
only in this document, in the authoring guide that reproduces it, and in
`tmp_path` test fixtures built from it.

`backend/content/campaigns/hollow-reach/v1/campaign.json`

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

`backend/content/campaigns/hollow-reach/v1/adventures/the-sunken-mill.json`

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

`backend/content/campaigns/hollow-reach/v1/definitions/bog-lurker.json`

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
`mill-floor` is reachable from `mill-approach` (R11) and has no `exits`, so it is
terminal (R10); `bog-lurker` is referenced by a scene (R14) and its name is
unique (R15); no scene places a definition twice (R16); the omitted
optional fields — `npc_intent`, `creatures`, `pressure` on `mill-approach`, and
`exits` on `mill-floor` — take their defaults, which is legal and is how absence
is expressed.

---

## 5. The service surface — contract (D10)

Every function below is **synchronous**. They read local files and touch no
database and no network, so there is nothing to await; making them `async`
would require a new dependency (`aiofiles`) or a fake-async wrapper, and would
stop the Typer command from calling them without an event loop. They therefore
also break the "`AsyncSession` first, positionally" convention of
`backend-stack.md` — that convention governs database services, and this module
has no session to take.

**No caching.** `load_campaign` re-reads and re-validates on every call. A
campaign is a handful of small JSON files; the cost is negligible beside the LLM
call in whose turn it sits, and an `lru_cache` here would buy microseconds while
introducing a cache-invalidation question (and a `cache_clear()` trap for every
test that repoints `CONTENT_ROOT`). If phase 8 ever measures a real cost, phase
8 adds the cache — the invalidation question is trivially answered by the
versioning rule, since a published version is never edited.

```python
# backend/app/modules/content/service.py

CONTENT_ROOT: Path
VERSION_PATTERN: re.Pattern[str]        # ^v[0-9]+$ — written once, used by the CLI too


def list_campaign_ids() -> list[str]:
    """Campaign *directory* names under CONTENT_ROOT/campaigns, sorted.
    Directories only -- a file lying directly under campaigns/ is ignored.
    Returns [] when the directory does not exist. Raises nothing."""


def list_versions(campaign_id: str) -> list[str]:
    """Conformant version directory names for a campaign, sorted by their
    numeric suffix ascending. Directory names not matching VERSION_PATTERN are
    ignored -- the CLI is what reports them (R3, §7.1).
    Raises ContentNotFoundError if the campaign directory does not exist."""


def load_campaign(campaign_id: str, version: str) -> LoadedCampaign:
    """Read and fully validate one campaign version.
    Raises ContentNotFoundError if the version directory does not exist.
    Raises ContentInvalidError carrying *every* schema, read and referential
    problem found (§6)."""


def load_scene(campaign_id: str, version: str, scene_id: str) -> Scene:
    """Raises ContentNotFoundError if the scene is not in that campaign
    version; otherwise as load_campaign."""


def load_definition(campaign_id: str, version: str, definition_id: str) -> Definition:
    """Raises ContentNotFoundError if the definition is not in that campaign
    version; otherwise as load_campaign."""
```

### 5.1 Every id argument is validated before a path is built

`campaign_id`, `scene_id` and `definition_id` must match the `ContentId` pattern
(`^[a-z0-9]+(-[a-z0-9]+)*$`) and `version` must match `VERSION_PATTERN`
(`^v[0-9]+$`) — **checked in the function body before any path is joined to
`CONTENT_ROOT`**. A non-conforming value raises `ContentNotFoundError` carrying
that raiser's pinned `relative_path` from §6.1, and the function reads nothing:
no `Path` is built, no `exists()` is called, no file is opened. So
`load_campaign("../../app", "v1")` and `load_scene("hollow-reach", "v1",
"../campaign")` are ordinary not-found errors, never a traversal out of the
content root and never a filesystem read. `list_versions` validates
`campaign_id` the same way, raising `campaigns/<campaign_id>`.

This is inside the existing loader functions — no new module, no new dependency,
no sanitisation helper. Phases 5, 7 and 8 feed these arguments from client
requests, so the validation belongs at the module boundary that owns the path.

`load_scene` and `load_definition` are implemented over `load_campaign`, so a
single-entity read is never served from an unvalidated tree. They exist rather
than exposing `LoadedCampaign.scenes[...]` to callers because turning a
`KeyError` into this module's own error type is the module's job, not phase 8's.

There is **no `latest_version`**. Nothing in Stage-01 calls it: the CLI walks
every version, and phase 5 will add it when it has a use for "the newest
campaign version" — a function with no caller is not a contract.

**Callers use the module reference for functions *and* for module attributes**
(D10): `from app.modules.content import service as content_service`, then
`content_service.load_campaign(...)` and `content_service.CONTENT_ROOT`. Nothing
imports a service function or a service constant by name — `from .service import
CONTENT_ROOT` rebinds the value into the importing module at import time, and
`monkeypatch.setattr(service, "CONTENT_ROOT", ...)` then silently misses, which
is the exact failure D10 exists to prevent.

---

## 6. Errors

`backend/app/modules/content/errors.py`:

```python
class ContentError(Exception):
    """Base for every content failure."""


class ContentNotFoundError(ContentError):
    def __init__(self, relative_path: str) -> None:
        self.relative_path = relative_path
        super().__init__(f"content not found: {relative_path}")


class ContentInvalidError(ContentError):
    def __init__(self, campaign_id: str, version: str, errors: list[str]) -> None:
        self.campaign_id = campaign_id
        self.version = version
        self.errors = errors
        detail = errors[0] if errors else "no detail"
        super().__init__(
            f"{campaign_id}/{version}: invalid content ({len(errors)} problem(s)): {detail}"
        )
```

`ContentInvalidError` is **never raised with an empty `errors` list** — a load
either has problems or succeeds. The `errors[0] if errors else` guard exists so
a future caller constructing one wrongly gets a wrong message rather than an
`IndexError` from inside an exception constructor.

### 6.1 `relative_path`, pinned per raiser

Always relative to `CONTENT_ROOT`, forward slashes, no leading slash.

| Raiser | Condition | `relative_path` |
|---|---|---|
| `list_versions` | the campaign directory does not exist | `campaigns/<campaign_id>` |
| `load_campaign` | the version directory does not exist | `campaigns/<campaign_id>/<version>` |
| `load_scene` | the scene id is not among the campaign's scenes | `campaigns/<campaign_id>/<version>/scene/<scene_id>` |
| `load_definition` | the definition id is not among the campaign's definitions | `campaigns/<campaign_id>/<version>/definitions/<definition_id>.json` |

The last two name nothing the loader opened — the lookup is against the loaded
campaign, not the filesystem. Pinned anyway, because it is the string QA asserts
on and it is what an author needs to see.

**Which `relative_path` a non-conforming id argument raises.** In `load_scene`
and `load_definition`, a bad `campaign_id` or a bad `version` raises
**`load_campaign`'s** row — `campaigns/<campaign_id>/<version>` — because the
campaign version is what could not be located; only a bad *entity* id raises the
entity row. The guard clauses therefore run in that order: campaign and version
first, entity id second (§5.1).

**`scene/<scene_id>` is a logical address, not a path** (P1-D20): scenes live
inside their adventure file, so there is no `scenes/` directory and no
`<scene_id>.json` to name. The singular `scene/` and the absent `.json` are
deliberate — they cannot be mistaken for a file that ought to exist.

### 6.2 The `errors[]` message grammar

Every entry of `ContentInvalidError.errors` is:

```
<path relative to the version directory>: [<TAG>] <detail>
```

| Tag | Means |
|---|---|
| `[READ]` | the file could not be read or is not valid JSON |
| `[SCHEMA]` | the file parsed but failed Pydantic validation |
| `[R2]`, `[R4]` … `[R16]` | the numbered referential rule of §11 that failed |

**`[R3]` never appears in `errors[]`**: R3 is a CLI check (§7.1), not a
load-time rule.

R1 has no tag of its own: it *is* the readability and schema-validity of
`campaign.json`, so its failure is reported as `[READ]` or `[SCHEMA]`.

Examples:

```
adventures/the-sunken-mill.json: [R9] scene 'mill-approach': exit targets unknown scene 'under-whee'
adventures/the-sunken-mill.json: [SCHEMA] scenes.1.truth.0: String should have at least 1 character
campaign.json: [SCHEMA] Input should be a valid dictionary
definitions/bog-lurker.json: [READ] Expecting ',' delimiter: line 8 column 3 (char 214)
```

**A rule that fails inside a scene names its adventure file and puts the scene
id in the detail** (R8, R9, R12, R16). The path segment is the file an author
opens; the scene id is how they find the place in it. QA asserts on the path and
the tag, so the detail wording stays free — but the scene id must be in it.

- The `[SCHEMA]` detail is built from **`ValidationError.errors()[0]` and that
  error only** — one file that fails validation is one `errors[]` entry, never
  one per Pydantic complaint, so the list stays readable and the sort stays
  stable. The detail is `".".join(str(p) for p in error["loc"])` + `": "` +
  `error["msg"]`. **When `loc` is empty** — a model-level error — the location
  segment and its colon are omitted entirely; there is never a `": : "` in a
  message.
- The list is **sorted by the message string**, so output is stable between
  runs.
- **The rule prefix is the contract, not the wording.** With no route and no
  `openapi.json`, `errors[]` *is* the seam between backend-dev and qa-backend.
  QA asserts on the path and the `[TAG]`, and **never** on Pydantic's `msg`
  text, which is not version-pinned and changes between Pydantic releases.

### 6.3 One rule for partial failures

**Any failure to read or parse any file under the version directory becomes one
`errors[]` entry, and the walk continues.** There is no branch table: an
unreadable file, malformed JSON and a schema violation are all one entry each,
and the load as a whole fails once at the end with all of them. **Under
`adventures/` and `definitions/` a *missing* file is never a read failure** —
under the glob model nothing tries to open it, and its absence surfaces as
`[R4]` or `[R12]`. `campaign.json` is the exception: it is opened by name, so a
missing one *is* reported, tagged `[READ]` or `[SCHEMA]` per R1, and reported
alone (below).

**Only three kinds of file are ever opened**, so a malformed scene is a
`[SCHEMA]` entry on its **adventure** file, located by Pydantic's own `loc` —
`scenes.2.truth.0`. An adventure that fails `[READ]` or `[SCHEMA]` takes its
scenes with it: it is excluded from every later rule exactly as an R6 failure
is, and it produces no further findings about itself. One broken adventure is
one entry, not one per scene — the honest cost of P1-D20, and the reason the
`loc` path is part of the message.

The single exception: **if `campaign.json` itself is missing, unreadable or
schema-invalid, that is the only reported problem**, because nothing else in the
tree can be located without its adventure list.

**Phase 1 defines no `ErrorCode` and raises no `ApiError`.** Content loading is
not a request-layer concern here; phases 5 and 8 decide how a content failure
surfaces on the wire and own that mapping.

---

## 7. The CLI

```
app content validate
```

No arguments and no options. It validates **every** campaign and **every**
version directory found under `CONTENT_ROOT/campaigns`. There is no
`--campaign` and no `--version`: nothing needs them, and validating everything
is what an author, QA and a reviewer all actually want.

| Stream | Content |
|---|---|
| stdout | One line per valid campaign version: `<campaign_id>/<version>: ok` |
| stderr | One line per problem: `<campaign_id>/<version>: <error>` — the entries of `ContentInvalidError.errors` — plus the `[R3]` line of §7.1, the no-version line of §7.1 and the no-campaigns line below |

Stdout is the result data (`backend-stack.md`: a command that produces data
writes only that data to stdout); problems are diagnostics and go to stderr.

**The command emits no structlog records at the default log level**, so stderr
contains problem lines and nothing else, and QA may assert its contents
line-exact. `configure_logging()` still runs in `cli.py`'s callback — it
configures a logger, it does not write one.

| Exit code | Condition |
|---|---|
| `0` | At least one campaign version was found, every one is valid, no non-conformant version directory exists, and every campaign has at least one conformant version |
| `1` | Any campaign version failed validation, any version directory name is non-conformant, any campaign has no conformant version directory, or no campaign was found at all |

A silent pass over an empty content tree is a trap, so an empty tree is a
failure with `no campaigns found under <CONTENT_ROOT>` on stderr. **The command
exiting 1 between steps 1.1 and 1.3 is correct behaviour, not a defect** (§8) —
originally because `backend/content/campaigns/` did not exist yet, and in the
P1-D20 rework because the shipped campaign is still in the pre-amendment layout
until 1.3 migrates it.

Neither `ContentNotFoundError` raiser can fire inside the command's own walk —
it only ever names campaigns and versions it has just listed — so the command
defines no output for one.

### 7.1 R3 is a CLI check, not a load-time rule

`list_versions` filters non-conformant directory names out, so `V1`, `v1.0` and
`version-1` would otherwise vanish silently — the same trap as the empty tree.
The command therefore lists the campaign's subdirectories itself and reports
every name that `content_service.VERSION_PATTERN` does not match:

```
hollow-reach/v1.0: [R3] version directory name must match ^v[0-9]+$
```

and exits 1. The pattern lives in `service.py` and is used from there; it is
never re-written as a literal in `commands.py`.

**A campaign directory with no conformant version directory at all** — empty, or
holding only non-conformant names — writes

```
<campaign_id>: no version directory found
```

to stderr and fails. Without this the state has no defined exit code, and step
1.3 passes straight through it the moment the author creates
`campaigns/greenhollow/`.

### 7.2 `commands.py` reads `CONTENT_ROOT` at call time

```python
# backend/app/modules/content/commands.py
from app.modules.content import service as content_service

...
root = content_service.CONTENT_ROOT      # inside the command body, never at import
```

`from app.modules.content.service import CONTENT_ROOT` would bind the value at
import time and defeat `monkeypatch.setattr(service, "CONTENT_ROOT", tmp_path)`,
making every CLI test run against the real tree. This is the module-attribute
half of D10 (§5).

### 7.3 Registration in `app/cli.py`

Stage README §3 names `app/cli.py` as the one file phases 1, 2 and 3 share.
**The existing `openapi` block stays first; phases 1, 2 and 3 append their own
blocks below it, in phase order.** Phase 1's change is exactly one import line
and one registration line:

```python
from app.modules.content.commands import content_app

cli.add_typer(content_app, name="content")
```

Nothing else in `app/cli.py` is touched — not the `openapi` block, not the
callback, not the imports above it.

The convention phase 1 sets and phases 2 and 3 follow: **a module owns its Typer
sub-app in `<module>/commands.py` and exports it as `<module>_app`; `app/cli.py`
only imports and registers.**

---

## 8. The test-facing surface

`backend/tests/content/` mirrors the module (D1, qa-checklist). qa-backend can
import and call:

- `from app.modules.content import service, schemas, errors`
- `from app.modules.content.commands import content_app` — driven with Typer's
  `CliRunner`, as `tests/test_cli.py` already does for `openapi export`.
  **Invoked as `CliRunner().invoke(content_app, [])`, with no `"validate"` in
  the argument list**: Typer collapses a single-command app, so `content_app`
  *is* the command and the name `validate` exists only through the `cli` group
  (`CliRunner().invoke(cli, ["content", "validate"])`, which is unaffected).

**`backend/tests/content/__init__.py` is required**, as every landed test
package has one: `backend/tests/users/test_service.py` already exists, so an
`__init__.py`-less `tests/content/test_service.py` gives pytest two modules of
the same basename and an import collision.

**Which Typer app a CLI assertion drives is contract.** `content_app` has no
callback, so `configure_logging()` never runs under it; every CLI behaviour
assertion therefore runs against `content_app` with an empty argument list,
**except the "no log record" assertion, which must run against `cli` from
`app.cli`** — the only path on which the callback configures logging — and must
check *stdout* as well as stderr, because an unconfigured structlog
`PrintLogger` writes to stdout and would otherwise corrupt the result data
unnoticed. Pinned per criterion in
`step-1.1.md` §6.

**Fixture content is built in `tmp_path` per test and is never committed.**
A test that needs a broken tree writes JSON files into `tmp_path` and does
`monkeypatch.setattr(service, "CONTENT_ROOT", tmp_path)`. This is why
`CONTENT_ROOT` is read inside function bodies (§2, §7.2). There is deliberately
**no** second content tree under `backend/tests/`: a committed fixture corpus
would be a second thing to keep in sync with the schema. The worked example of
§4.1 is the shape fixtures should be built from.

**The shipped-tree test belongs to step 1.3, not to step 1.1.** Every step-1.1
test repoints `CONTENT_ROOT` at a `tmp_path` tree and no step-1.1 criterion
concerns the real `backend/content/`; the unmocked test that loads the shipped
campaign, and the CLI assertion that a non-empty tree exits 0, belong to
**step 1.3**.

**In the P1-D20 rework, the suite is expected to be red between 1.1 and 1.3, and
for a different reason than when this phase was first built.** Those shipped-tree
tests already exist and already pass against the old layout. The moment step 1.1
lands `Adventure.scenes: list[Scene]`, the shipped campaign — which still carries
`"scenes": ["village-green", …]` — stops validating, so
`tests/content/test_shipped_tree.py` and the `app content validate` check go red
until **step 1.3** re-shapes the campaign. **That red is the rework working, not
a defect**, and no agent is to repair it by touching `backend/content/` from step
1.1 or by relaxing the schema. It clears in 1.3 and only in 1.3.

That unmocked step-1.3 test is both the phase's "prove the authored set is valid
and readable" evidence and the standing guard on §2's path resolution: it fails
loudly if `CONTENT_ROOT` ever stops pointing at the shipped tree.

### 8.1 Notes that will otherwise cost time

- **`cp .env.dist .env` is required before anything runs.** `cli.py`'s callback
  calls `configure_logging()`, which calls `get_settings()`, and `Settings`
  declares `database_url` with no default — so `app content validate` raises a
  `ValidationError` before it does any work when `.env` is absent. Separately,
  `compose.yaml` declares `env_file: .env` on `app-cli`, so `make backend-test`
  cannot even start a container without it. The repository ships only
  `.env.dist`.
- `filterwarnings = ["error"]` (D31, D36) applies here as everywhere.
- The suite stays synchronous — these functions are synchronous, so no
  `pytest-asyncio` is needed or wanted (D9).
- **Typer's own `CliRunner` (`typer>=0.27.2`) captures stdout and stderr
  separately and unconditionally**, so `result.stdout` and `result.stderr` are
  both available; the §7 stream split is therefore assertable.
- QA asserts on the path and the `[TAG]` of a message, never on Pydantic's
  `msg` wording (§6.2).
- No database, no `TestClient`, no `dependency_overrides` are involved in this
  module's tests.

---

## 9. Documentation phase 1 owns

### 9.1 `docs/modules/content.md` — the authoring guide

The first entry in `docs/modules/`, and the phase's schema-documentation
deliverable. It must be complete enough that an agent could author a conformant
campaign from it **alone**, without reading `backend/app/modules/content/`:

- the directory layout and the versioning rule (§4);
- every model, every field, its JSON key, its type, whether it is required, its
  default, and one sentence on what it is for (§3);
- every constraint that will actually reject a file — `extra="forbid"`, the
  `ContentId` pattern, `ProseText`'s strip-then-non-empty rule, every
  `min_length` / `ge` / `le` bound;
- the full rule list of §11, with its `[R<n>]` tags, so an author can map a
  reported problem back to a rule;
- the complete worked example of §4.1, reproduced verbatim — **three files**;
- **why the layout has the granularity it has**: an adventure is one file
  because its scenes belong to it alone, and a definition is its own file
  because it is campaign-scoped and shared between adventures (§4, P1-D20);
- **one sentence on what a `Definition` is**, in the template/instance terms of
  §3.4: a definition is the campaign-scoped template, and what appears in a
  scene during a run is an instance of it (P1-D21);
- the two rules a generator gets wrong by default, stated in these words:
  **a scene is facts, intentions and consequences, never a script**, and
  **an exit condition is prose the agent judges, never a flag, a variable or a
  comparison**.

Stage README §5 fences the LLM content-generation CLI out of Stage-01: **this
document is the deliverable, not a generator.**

`backend/app/modules/content/README.md` stays short — Owns / Surface / Notes, in
the shape of `backend/app/modules/users/README.md` — and **links** here rather
than copying the field reference.

### 9.2 Corrections phase 1 owns (stage README §9)

| File | Section | Correction |
|---|---|---|
| `docs/README.md` | *Modules* | **Applied in the first pass; verify only.** Replace "*None yet — the first module doc lands with the first subsystem.*" with a table carrying the row `[modules/content.md](modules/content.md) \| The adventure-content schema, its directory layout and versioning, and the authoring guide` |
| `docs/general/model.md` | *Static files* | The content root is `backend/content/`, not `content/` — with the one-clause reason from §2. |
| `docs/general/model.md` | *Static files* | `npcs/` and `monsters/` become one `definitions/` directory holding one `Definition` entity, which always carries a stat block — the same doc already rules there is no npc/monster split. |
| `docs/general/model.md` | *Static files* | **There is no `scenes/` directory.** A campaign version is `campaign.json`, `adventures/<id>.json` — the adventure *and its scenes* — and `definitions/<id>.json`. State the reason in one clause: a scene belongs to one adventure, a definition is shared between them (P1-D20). |
| `docs/general/model.md` | *Static files* | The scene-field line becomes the pinned set: `truth[]`, `npc_intent?`, `consequences[]`, `hidden[]`, `creatures[]`, `exits[]` (a **list**, not a map), `pressure?`. |
| `docs/general/model.md` | *Static files* | `campaign.json` also carries the **seed player character**, and each adventure carries a prose **`intro`** and an `entry_scene`. |
| `docs/general/model.md` | *Content lives in git, runs pin a version* | State the mechanism: a version is a `v<n>` directory under the campaign, served whole, never edited in place. |
| `docs/general/architecture.md` | *System components* → **Adventure content** | Strike "Authored by an LLM once through a `generate_adventure` CLI that prompts with the SRD and enforces the schema". Content is **hand-authored**, validated by `app content validate`, and reviewed as a diff. |
| `docs/general/requirement-map.md` | *Task requirements*, row 3 | State the player-capability reading of stage README §8: every **player** capability has a surface; operator capabilities such as content validation are CLI-only by design, because putting them in the player UI is exactly what Medium-8 penalises. (Phase 11 makes the full argument.) |

Phase 1 does **not** touch `docs/general/glossary.md`: the *Definition* entry is
still accurate, and the *seed player character* term is assigned to phase 5 by
stage README §9.

### 9.3 Three rows phase 1 adds to the stage README

**The only edit phase 1 makes to another plan document.** Step 1.2 applies all
three; the exact wording is in `step-1.2.md` §7.

Two go to §9's doc-correction register, which claims to be the single home for
corrections and does not list these:

| Contradiction | File | Owning phase |
|---|---|---|
| The static-file tree's content root, its `scenes/` directory, the `npcs/` + `monsters/` split, the scene-field line, the missing `intro` / `entry_scene` / seed character, and the unstated version mechanism — enumerated in `roadmap/Stage-01/phase-01/shared-knowledge.md` §9.2 | `general/model.md` | 1 |
| The tool table's `get_monster(name)` row — with one `Definition` entity the binding is id- or name-addressed over `definitions`, and its final name and argument are phase 8's to pin | `general/architecture.md` | 8 |

One goes to §7's open-decisions register, because §10.3 below is a note and not
a control — without a register row, phase 8 ships the leak and phase 9 finds it:

| Open decision | Owning phase |
|---|---|
| **How `hidden` and `Secret.dc` are projected out of any scene-derived tool result** before it reaches the visible trace (this document §10.3) | 8 |

---

## 10. Known gaps, recorded not solved

1. **A `damage` dice expression is not validated at load time** — phase 3's
   parser is the single authority on that grammar and lands in parallel. A
   malformed expression surfaces as a tool error during a turn, not at load.
2. **An exit `condition` is prose and is therefore unverifiable** — the accepted
   consequence of `model.md`'s "situational facts have no flag store", already
   recorded there as known gap 2.
3. **`hidden` must be projected out before it can be seen.** `Scene.hidden` and
   `Secret.dc` are DM-only. **Any phase-8 tool result derived from a `Scene`
   must project `hidden` and `Secret.dc` out before it reaches the visible
   trace**, or phase 9's trace pane leaks the secret and its difficulty — which
   would break "the fact that a roll happened is not a tell" (app-vision).
   Recording it now costs nothing; discovering it in phase 9 is a redesign.
   **Carried out of this phase as a row in stage README §7's open-decisions
   register, owned by phase 8** (§9.3) — a note in this document is not a
   control.
4. **Proficiency is not modelled, and Stage-01 resolves every check on the raw
   ability modifier.** There is no `level`, no proficiency bonus, no skill list
   and no authored player attacks: a monster's `to_hit` is the complete bonus
   its author baked in, and everything else is `d20 + (score − 10) // 2` against
   an authored DC. This is a deliberate simplification of 5e, not an omission to
   be quietly repaired by an implementer.
5. **Nothing is bounded.** No string and no list has a maximum length, so
   content size is limited only by an author's restraint. Phase 8's prompt
   composer inherits that entirely and owns any budget or truncation policy.
6. **Content integrity is loader-enforced, not database-enforced** —
   `model.md` known gap 3, unchanged; `app content validate` is the enforcement.
7. **Nothing validates prose quality.** A scene whose `truth` is grammatical and
   meaningless passes every rule. The human-in-the-loop review in step 1.3 is
   the only control.

---

## Landed decisions

Phase-1 decisions use the `P1-D<n>` scheme so they never collide with phase 0's
`D<n>`. Append here; one heading per decision, newest last; never rewrite
another agent's entry.

### P1-D1 — Content lives at `backend/content/`, resolved from `__file__`

`CONTENT_ROOT = Path(__file__).resolve().parents[3] / "content"` in
`service.py`. Reason: the Dockerfile's `COPY backend/ ./`, the compose bind
mount `./backend:/app` and a host-side `uv run pytest` all put the tree at the
same relative path, so the location needs no Dockerfile line, no compose mount,
no `Settings` field and no environment variable.

### P1-D2 — Content JSON is `snake_case`, and `CamelModel` is not used

Content models derive from a module-local `ContentModel(BaseModel)` with
`extra="forbid"` and `frozen=True`, and their JSON keys are identical to their
Python field names. Human-readable strings use the `ProseText` alias
(strip-then-non-empty); ids use `ContentId`. Reason: content is not the wire —
`CamelModel` exists for responses, and a 1:1 mapping between the authoring
guide, the JSON key and the attribute removes a class of authoring mistake that
an alias layer would hide.

### P1-D3 — One `Definition` entity, one shape, one `definitions/` directory

NPCs and monsters are one model, and **`stat_block` is required on all of
them** — there is no optional branch and no npc/monster split. A definition
placed in a scene becomes an object row whose HP, max HP and AC are promoted
columns in phase 5, so an absent stat block would leave phase 5 inventing
mechanics. "Cannot fight" is expressed as `attacks: []`, not as a missing stat
block.

### P1-D4 — A scene's occupants are one `creatures[]` list of placements

`{definition, count}`, covering a named NPC (`count: 1`) and a monster group
identically, and a definition appears at most once per scene (R16). Reason:
phase 5's eager instantiation is then one uniform walk, `count` is the one fact
it cannot invent, and forbidding duplicates keeps the instance key out of list
order.

### P1-D5 — `exits` is a list of objects, not a map

`{to, description, condition?}`. Reason: a direction-keyed map implies a map the
game does not have, a scene-id-keyed map duplicates the value and forbids two
routes to one place, and only an object can carry `description` and `condition`.

### P1-D6 — An exit condition is prose the agent judges; a terminal scene has no exits

There is no condition language and no flag reference, because `model.md` rules
that situational facts have no flag store. A scene with `exits: []` ends the
adventure, and every adventure must contain one (R10).

### P1-D7 — Content declares no items and no fixtures in Stage-01

Scene contents are creatures only; `model.md`'s `item` and `fixture` object
kinds get no content-side declaration, so phase 5 instantiates creatures only.
Reason: loot and scenery are narrated, and anything that must persist lands in a
creature's inventory through `update_object` — a whole content entity for
declared items has no other Stage-01 consumer. **Upheld by the owner after
review.**

One consequence phase 5 inherits, recorded here because this decision causes it:
the two halves of a creature are not field-identical. `SeedCharacter` carries
`inventory` and `StatBlock` does not; `Definition` carries `disposition` and
`SeedCharacter` does not. So phase 5's single creature-state model needs **an
inventory field defaulted to `[]`** for every non-player creature and **a
disposition field defaulted to empty** for the player's. Both are trivial, and
both are inventions, so both are named here rather than discovered there.

### P1-D8 — Loaders are synchronous and uncached

They read local files, so there is nothing to await and no `AsyncSession` to
take; a cache would buy microseconds beside an LLM call and introduce an
invalidation question and a `cache_clear()` trap in every test that repoints
`CONTENT_ROOT`.

### P1-D9 — `load_campaign` collects every problem and raises once

`ContentInvalidError` carries `errors: list[str]`, sorted, each
`"<path>: [<TAG>] <problem>"` with `TAG` ∈ {`READ`, `SCHEMA`, `R2`…`R16`}. Any
read, parse, schema or referential failure is one entry and the walk continues;
only an unusable `campaign.json` is reported alone. Reason: one validation path
serves both the loader and the CLI (DRY), an author fixes a tree in one pass,
and the tag is what makes an individual rule provable by QA — without it, an
implementation that silently skips a rule still passes.

### P1-D10 — Phase 1 defines no `ErrorCode` and no `ApiError`

`ContentError` / `ContentNotFoundError` / `ContentInvalidError` are plain
exceptions in `app/modules/content/errors.py`. Reason: content loading is not a
request-layer concern in this phase; phases 5 and 8 own how a content failure
reaches the wire.

### P1-D11 — A version is a `v<n>` directory, served whole, never edited

`VERSION_PATTERN = ^v[0-9]+$`, defined once in `service.py`. `list_versions`
ignores non-conformant names and the **CLI reports them (R3) and exits 1**, so
nothing vanishes silently. There is no `latest_version`: nothing in Stage-01
calls it, and phase 5 adds it when it has a use. Reason: the directory name
already expresses everything "runs pin a version" requires, so a manifest, a
semver string or a `published` flag would be a second source of truth.

### P1-D12 — A module owns its Typer sub-app in `<module>/commands.py`

`content_app` in `app/modules/content/commands.py`; `app/cli.py` gains exactly
one import line and one `cli.add_typer(...)` line, appended below the existing
`openapi` block, and phases 2 and 3 append theirs below that in phase order.
Reason: `app/cli.py` is the one file phases 1, 2 and 3 share, so each phase's
footprint in it must be a single additive block. The `openapi` block stays
inline and is **not** retrofitted into a module — it belongs to no domain
module, `make generate-api` depends on it, and moving it would put a
cross-cutting change into the very file this convention exists to keep quiet.

### P1-D13 — Test content is built in `tmp_path`; the shipped tree is tested unmocked in step 1.3

Tests repoint `CONTENT_ROOT` with `monkeypatch.setattr`; no fixture content is
committed. The unmocked test over the real `backend/content/` tree — the
authored-set evidence and the standing guard on P1-D1 — is authored in step 1.3,
because `backend/content/` did not exist while step 1.1 was first built — and,
in the P1-D20 rework, because the shipped tree stays in the pre-amendment layout
until 1.3 migrates it.

### P1-D14 — The backend project stays installed in editable mode

`uv sync`'s default (editable) is what makes `app.__file__` resolve inside
`/app` — and therefore `CONTENT_ROOT` resolve to the bind-mounted tree — when
the `app` console script runs in `app-cli`. **Do not add `--no-editable` to any
`uv sync` invocation**; it would silently point `CONTENT_ROOT` at a
site-packages copy with no `content/` beside it. The unmocked test of P1-D13 is
what catches a regression.

### P1-D15 — Glossary spellings bind field names: `armour_class`

`docs/general/glossary.md` states its terms are used exactly as defined "in
code, in content and in the UI", and defines *Armour Class*. Not `armor_class`.

### P1-D16 — Proficiency is out; checks resolve on the raw ability modifier

No `level`, no proficiency bonus, no skills, no authored player attacks. A
monster's `Attack.to_hit` is the complete bonus. Reason: a level field with no
progression rules and no consumer is speculative surface, and `135.md` grades
agent knowledge, not 5e fidelity. Recorded as §10.4 so phase 8 does not discover
it mid-prompt.

### P1-D17 — `Definition.name` is unique within a campaign (R15, was R17)

Reason: it is the content-side precondition that makes a display-name lookup
over `LoadedCampaign.definitions` return at most one result — without it,
phase 8's creature tool has an ambiguity no amount of prompting fixes. One rule,
no new field.

### P1-D18 — Every id argument is validated before a path is built

`load_campaign`, `load_scene`, `load_definition` and `list_versions` check
`campaign_id` / `scene_id` / `definition_id` against the `ContentId` pattern and
`version` against `VERSION_PATTERN` **before joining anything to
`CONTENT_ROOT`**, and raise `ContentNotFoundError` with §6.1's pinned
`relative_path` when a value does not conform (§5.1). Reason: phases 5, 7 and 8
feed these from client requests, so `load_campaign("../../app", "v1")` must be a
not-found error and not a read outside the content root. It is a guard clause in
the existing functions — not a new module, a helper or a dependency.

### P1-D19 — An id mismatch never changes an entity's identity; only R6 drops the entity

**Amended by P1-D20, which removed the old R9 and renumbered the rest; the
paragraph below is the current statement.**

Every rule identifies an adventure or a definition by its **filename stem**, so
an `id` field that disagrees is reported and otherwise ignored. An adventure
failing **R6** — or failing `[READ]` or `[SCHEMA]` — is dropped from every later
rule (R7–R12), so it yields no further findings about itself, consistent with
R4's "the list is de-duplicated before any later rule is evaluated". Its scenes
go with it and are reported by nothing, because a scene is not a file and cannot
be an orphan. A definition failing **R13** is *not* dropped: it remains in the
loaded map under its filename stem and is still evaluated by R15. A scene has no
filename, so its identity is its `id` field and **R8** is what keeps that
identity unambiguous.

### P1-D20 — An adventure is one file, scenes included; definitions stay their own files

**Owner decision, taken after phase 1 first landed, and the shape phase 1 is
re-worked to.** A campaign version is exactly three kinds of file:

```
campaign.json                    campaign metadata + the seed player character
adventures/<adventure_id>.json   the adventure and its scenes, inline
definitions/<definition_id>.json campaign-scoped, shared between adventures
```

`Adventure.scenes` carries `Scene` objects, not ids. **Granularity follows
scope:** a scene belongs to exactly one adventure, so it lives inside it; a
definition is campaign-scoped by P1-D3 — the villain of adventure 1 returns in
adventure 3 — so it cannot.

Reasons, in the order they carry weight:

1. **It makes three rules unnecessary instead of enforcing them.** The old R7
   (a listed scene id has a file), R8 (a scene file is claimed by exactly one
   adventure, with its two-owner determinism clause) and R9 (a scene id equals
   its filename stem) existed only to police the multi-file layout. Containment
   states the same thing structurally, and a rule that exists only to police a
   layout is not a reason to keep that layout. One rule replaces all three:
   R8's scene-id uniqueness, which is needed because `LoadedCampaign.scenes` is
   flat and a run pins a scene id.
2. **An adventure is the unit an author and a reviewer actually work on.**
   Entry scene, exits and reachability are properties of the whole adventure;
   in the old layout they could only be checked by opening four files at once.
3. **A later stage that generates an adventure writes one file.** One model
   output, one atomic write, one diff to review — instead of N files that can
   half-land.
4. **The runtime is indifferent.** `LoadedCampaign`, every §5 signature and
   every phase-5/7/8 consumer read entities by id and are unchanged. The file
   layout is purely an authoring concern and stops at the loader — which is
   precisely why the owner's authoring preference decides it.

Accepted costs, stated rather than hidden: a malformed scene is one `[SCHEMA]`
entry on its adventure file rather than one on its own file (located by
Pydantic's `loc`, §6.3); an adventure file for a long adventure is long; and
`load_scene`'s not-found locator becomes the logical `scene/<id>` (§6.1).

The rule list is **renumbered to R1–R16** (§11 carries the old→new map).
P1-D19's drop semantics are amended there and in §11.

### P1-D21 — The term stays `Definition`; `npcs` and `creatures` are declined

**Owner question, ruled after review.** A `Definition` is a **template**: the
campaign-scoped description of a kind of creature, in `definitions/<id>.json`.
What exists in a scene during a run is an **instance** of it — the creature
object phase 5 creates `count` times, carrying current hit points, aliveness and
a disposition blob. The two have different lifetimes and different storage, and
phase 5 and phase 8 both have to tell them apart in one sentence.

- **`creatures/` is declined** because *creature* is already the instance's
  word — `model.md`'s object kinds, the player's creature object, phase 5's
  rows. Using it for both puts a homonym at the exact seam where the
  distinction is load-bearing.
- **`npcs/` is declined** because it names one of the two populations the single
  entity covers and reopens the question P1-D3 closes: a monster *is* an NPC
  here, and a directory called `npcs/` invites every author to ask whether a
  goblin belongs in it.
- **`docs/general/glossary.md` already commits to the term** — "*Definition* — a
  campaign-scoped NPC or monster stat block that scenes reference by id" — and
  its terms bind code, content and UI.

**The `definitions/` versus `creatures[]` tension is intentional and is not a
naming inconsistency.** `Scene.creatures` names *what is present in the scene*;
each entry's `definition` key names *the template it is cut from*. The same word
`definition` appears in the directory name and in the reference key, so an
author follows one word from the placement to the file. What §3.4 owed the
reader was the sentence explaining the pair, and §9.1 now requires the authoring
guide to carry it.


---

## 11. The referential rule list

The complete set of rules applied after every file has passed schema validation,
with the tag each failure carries in `errors[]` (§6.2).
`docs/modules/content.md` reproduces this list for authors.

| # | Where | Rule | Message names |
|---|---|---|---|
| R1 | load | `campaign.json` exists, is readable and passes schema validation. **Reported as `[READ]` or `[SCHEMA]`, not `[R1]`** — it has no tag of its own | `campaign.json` |
| R2 | load | `campaign.id` equals the campaign directory name | `campaign.json` |
| R3 | **CLI** | The version directory name matches `^v[0-9]+$` (§7.1) | the offending directory |
| R4 | load | Every id in `campaign.adventures` has an `adventures/<id>.json`, with no duplicates in the list. **The list is de-duplicated before any later rule is evaluated**, so a duplicate produces an `[R4]` entry and nothing else | `campaign.json` |
| R5 | load | Every `*.json` in `adventures/` is listed in `campaign.adventures` | the orphan adventure file |
| R6 | load | Each adventure's `id` equals its filename stem | the adventure file |
| R7 | load | `adventure.entry_scene` is the `id` of one of that adventure's own scenes | the adventure file |
| R8 | load | A scene `id` appears **at most once in the whole campaign** — twice in one adventure and once each in two adventures are the same failure | the adventure file holding the **later** occurrence, in `campaign.adventures` order and then `scenes` list order, so the message set is deterministic; the detail names the scene id |
| R9 | load | Every `exit.to` names a scene **in the same adventure**, and never the scene's own id | the adventure file; the detail names the scene id |
| R10 | load | Each adventure has at least one scene with `exits == []` | the adventure file |
| R11 | load | Every scene of an adventure is reachable from `entry_scene` by following exits, ignoring conditions. **The entry scene counts as reached, with no exits traversed**, so a one-scene adventure passes | the adventure file |
| R12 | load | Every `creatures[].definition` resolves to a `definitions/<id>.json` | the adventure file; the detail names the scene id |
| R13 | load | Each definition's `id` equals its filename stem | the definition file |
| R14 | load | Every `*.json` in `definitions/` is referenced by at least one scene (no dead content) | the orphan definition file |
| R15 | load | `Definition.name` is unique across the campaign's definitions, compared **case-insensitively** after `ProseText` stripping — `"Bog Lurker"` and `"bog lurker"` collide, because they are exactly the pair phase 8's name lookup cannot disambiguate | **every colliding definition after the first**, in sorted-id order, so the message set is deterministic |
| R16 | load | A definition appears at most once in a scene's `creatures` list | the adventure file; the detail names the scene id |

**Sixteen rules, renumbered by P1-D20.** The old R7 (a scene id resolves to a
scene file), R8 (a scene file is claimed by exactly one adventure) and R9 (a
scene id equals its filename stem) are **gone, not renumbered**: with scenes
inside their adventure file, all three state something the file layout now makes
true by construction. One new rule replaces them — R8, scene-id uniqueness
across the campaign — because `LoadedCampaign.scenes` is flat and a run pins a
scene id. The old→new map, for anyone holding the previous numbering:
R10→R7, R11→R9, R12→R10, R13→R11, R14→R12, R15→R13, R16→R14, R17→R15, R18→R16;
R1–R6 unchanged.

**Rules are scoped to what is actually claimed.** R6–R12 are evaluated only for
adventures listed in `campaign.adventures`. An unlisted `adventures/*.json` gets
`[R5]` and nothing else; an unreferenced `definitions/*.json` gets `[R14]` and
nothing else. One stray file produces one problem.

**What happens to an id-mismatched or unusable entity (P1-D19, as amended by
P1-D20).** The identity every rule uses for a file is its **filename stem**,
never the `id` field inside it, so a mismatch never shifts an entity's identity.
Beyond that:

- **R6 — an adventure whose `id` does not match its filename is dropped.** It
  gets the `[R6]` entry and is then excluded from R7–R12, so it produces no
  further findings about itself. Its scenes go with it and are reported by
  nothing, because they are not files and cannot be orphans.
- **An adventure that fails `[READ]` or `[SCHEMA]` is dropped the same way**
  (§6.3).
- **A dropped adventure contributes no scenes to R14**, so a definition that
  only that adventure referenced is reported `[R14]` as unreferenced. This is
  the deliberate answer and not an oversight: the alternative — remembering
  which definitions a dropped adventure would have referenced, in order to
  suppress an `[R14]` — is suppression machinery for a tree that is already
  broken. A dropped adventure therefore yields exactly two kinds of finding: its
  own `[R6]` / `[READ]` / `[SCHEMA]` entry, and an `[R14]` for each definition
  left with no other referrer.
- **R13 reports and continues.** A definition whose `id` does not match its
  filename is still evaluated by R15, under the filename-derived identity it
  already had.
- **A scene has no filename, so its identity is its `id` field**, and R8 is what
  keeps that identity unambiguous.

`seed_character` has no referential rule: it references nothing (§3.10).

---

## Steps

Cut by the `planner` in [steps.md](steps.md).

| Step | Spec | Contents |
|---|---|---|
| 1.1 | [step-1.1.md](step-1.1.md) | The content module — schema, loader, referential rules, the command-line check |
| 1.2 | [step-1.2.md](step-1.2.md) | The authoring guide, the docs index row, and the corrections this phase owns |
| 1.3 | [step-1.3.md](step-1.3.md) | The first campaign, authored from the guide and proven valid (human in the loop) |

1.1 and 1.2 run in parallel; 1.3 depends on both.
