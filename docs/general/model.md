# Data model

The domain model at entity level: what exists, what owns what, and why the
shape is that shape. Columns are not defined here — they are pinned by the step
spec that builds the module. Written before the game modules exist, so this is a
**design contract**: where this document and the code disagree, the code wins,
and this document gets corrected.

Three rules frame everything below and are not negotiable per-entity:

- **Postgres is the single source of truth** for character and world state. The
  LangGraph checkpointer holds the *conversation* and graph plumbing only, and
  is treated as rebuildable.
- **Authored content is static JSON in git**, never rows. Runs reference it by
  string id plus a pinned version.
- **No ORM relationships and no repository classes** (see
  [architecture.md](architecture.md)). Foreign keys exist in the schema; joins
  are written as queries in `service.py`.

## The entities

```
CONTENT  (static JSON in git, read-only at runtime)
  Campaign ──< Adventure ──< Scene ──> references definitions by id
      ├──< Definition  (NPC, monster stat block)
      └── campaign.json lists its adventures, in order

RUN  (Postgres, mutable)
  User ──< PlaythroughMember >── Playthrough ──> campaign_id + content_version
                                     ├──< AdventureRun ──> adventure_id
                                     │        └──< Encounter
                                     ├──< Object   (creature, item, fixture)
                                     ├──< Event    (what happened)
                                     └──< JournalEntry (what is true)   -- the journal

KNOWLEDGE
  SrdRule  (pgvector, owned by nobody, built by an ingest CLI)
```

- A **Playthrough is one run of one campaign**, not of one adventure. The
  player plays adventure after adventure inside it with the same character, so
  the character, the objects and the journal all hang off the Playthrough and
  survive adventure boundaries.
- **Everything under a Playthrough cascades from it.** AdventureRun, Object,
  Event and JournalEntry are owned rows with no independent existence; Encounter
  hangs off AdventureRun. Deleting the run deletes them all.
- **Campaign is a full domain entity** with a stable id — it just lives in a
  file rather than a table. Content ids carry **no foreign key**; referential
  integrity for content is loader-time validation, not a database constraint.
- **Definitions are campaign-scoped, not adventure-scoped.** A recurring NPC —
  the patron who hires the party, the villain who escapes in adventure 1 and
  returns in adventure 3 — is the normal shape of a campaign, and a monster
  stat block is reusable anywhere. So a Scene *references* a definition by id;
  it does not own one. This is the content-side mirror of objects hanging off
  the Playthrough: definition above the adventure, instance above the adventure
  run, and nothing about a returning character is per-adventure.
- **SrdRule belongs to no run.** It is global knowledge, rebuilt by a CLI, and
  survives every playthrough. Entities are named for what they hold, never for
  how it is stored — which is why this is not an `embeddings` table and a row
  is not a "chunk". How a rules section is split for retrieval is a column
  concern.
- One campaign and one adventure ship first. That is the **initial content set,
  not a ceiling**: more adventures and campaigns arrive as a new content
  version.

## The decisions behind the shape

### All ids are ULID

Every primary key in the domain is a ULID, including the pre-existing `users`
and `sessions` tables — one id strategy, no exceptions. ULIDs are
time-sortable, so a monotonic id doubles as a stable ordering key and no table
needs a `bigserial`. Event ordering is therefore by id, and the id is a ULID.
How the value is stored and rendered (a 26-character Crockford base32 string) is
the backend's business, not a modelling decision.

### Content lives in git, runs pin a version

A playthrough names the content revision it started with. Loaders serve exactly
that revision, so editing a scene never mutates a save in progress, and a
campaign extended with a fourth adventure ships as a new version that only new
runs pick up. Existing runs finish what they started — which is why objects can
be instantiated eagerly (below) with no backfill path.

**The mechanism**: a version is a `v<n>` directory under the campaign,
served whole by the loader and never edited in place.

### Settings live on the run

Model, temperature, DM personality and any system-prompt override belong to the
Playthrough, so a save replays with the tone it was played at. There is no
user-level settings row and no override chain. Personality is referenced by the
id of a prompt file, never as stored prompt text.

### Ownership lives on the membership row

Ownership is a role on `PlaythroughMember`; the Playthrough deliberately
carries no owner column, so there is one source of truth and authorisation is a
join. One member row per run today; the table is the only concession the model
makes to the multiplayer capstone (the second being one character per member).

### One generic `objects` table, campaign-scoped

Every interactable thing — the player character, allies, monsters, items,
fixtures — is one row in `objects`, owned by the **Playthrough**, so a goblin
that lost an arm in adventure 1 still has one arm in adventure 2. Instance keys
are deterministic and stable across a run, so content can name an instance
without a lookup table.

**Kinds are `creature`, `item`, `fixture`.** There is no `npc`/`monster` split:
a monster *is* an NPC, and "monster" only means "ships a stat block and is
usually hostile" — a content-side trait, not a storage kind. The player
character is likewise not a kind of its own; it is a creature identified by the
user who owns it.

One generic table buys uniform targeting, one `update_object` tool instead of
several, and campaign-scoped character state for free. It costs schema
enforcement, so:

> **Binding rule.** Every write to an object's state blob is validated against
> a Pydantic model selected by `kind`, and the API still serves a strongly typed
> resource built from that blob — the wire contract is typed even though storage
> is generic. Without this rule the "deterministic mechanics" layer is
> decoration.

With three kinds, **one creature model covers PC, ally and monster alike**;
character-sheet specifics (class, background, portrait) are a section of that
model, not a fourth kind. Hit points, maximum hit points, armour class and
aliveness are promoted out of the state blob into real columns, because they are
read on every turn and are the only fields a database constraint can actually
guard. Abilities, inventory, disposition, injuries and improvised traits stay in
the blob.

Objects are instantiated **eagerly when the run starts**: everything the pinned
content version declares, across all its adventures. No lazy creation during
play, no half-populated scenes.

### Position

The player's creature holds the scene it is in, and **that is the party's
position** — there is no second copy on the adventure run. The active adventure
is the AdventureRun whose status says so.

### Combat

Hit points and conditions already live on object rows, so an Encounter only
holds what is transient to one fight: an ordered participant list, a round
counter and a turn pointer. Participant state is never duplicated into it.

### Situational facts have no flag store

"The alarm was raised", "the village turned hostile" are **journal entries**,
not columns. Consequence, accepted deliberately: content **cannot
deterministically gate an exit** on a flag, because no flag exists for code to
read. Situational conditions are written as scene *truth* and judged by the
agent, which matches "facts + intentions + consequences, not scripts" — and
means a mis-retrieved journal entry can un-raise an alarm.

### Events and journal are two things: what happened vs what is true

**An event is what happened. A journal entry is what is true.**

**Events** are system-written, complete and ordered: narration, player input,
dice rolls, tool calls, errors and token cost in one append-only stream. The
trace panel, roll log and cost display are one ordered query with a filter, and
run cost is a sum over it — there is no denormalised total. Hidden rolls are
written with DM visibility and filtered out on read, so the audit trail survives
even when the player does not see it. Nothing is pruned and nothing is retrieved
by meaning: events are the evidence of how the agent behaved.

**Journal entries** are agent-written and curated, because campaigns outlive
context windows. Chat history is a window, not storage: it gets summarised, and
a summariser discards exactly the flavour that matters (a nickname the player
coined for an NPC). Adventure-sized state may fit in context; **campaign**-sized
state will not. So durable canon is written deliberately via
`add_journal_entry`, embedded on write, and retrieved as *top-k by similarity
plus the most recent N unconditionally* — the DM must not depend on choosing to
look. Entries are classified (a durable naming fact outranks a one-off outcome
in retrieval) and may cite the event they came from, which is the only link
between the two.

The journal is **not a transcript**: entries are facts, not prose.

*Rejected alternative — one table.* Collapsing them forces one of two losses:
embed every narration line, and retrieval quality and cost collapse (the journal
becomes the chat history with worse ergonomics); or carry a nullable embedding on
the hottest and largest table, fusing two lifecycles — never pruned versus
curated — and two access patterns — ordered scan versus similarity search.

### One embedding model, two tables

Journal entries and SRD rules share the embedding model, pinned in settings
with the dimension fixed in the migration, so they also share the ingest path,
the similarity operator and the cost line. Each vector row records which model
embedded it, so a re-embed is detectable.

They do **not** share a table. A shared pipeline is not a shared shape: a
journal entry is owned by a playthrough, cascades with it, points at an object
and is classified; an SRD rule is owned by nobody, is replaced wholesale by a
re-ingest, and cites a section and a position within it. *Rejected alternative
— one `embeddings` table with a scope key.* Every column above turns nullable,
the foreign key to the playthrough stops being enforceable, and two lifecycles
— cascade-with-the-run versus rebuild-the-corpus — hide behind a
discriminator.

### The checkpointer is the library's, not ours

LangGraph's `AsyncPostgresSaver` creates its own tables through its own
`setup()`, in a dedicated **`checkpoints` schema** in the same database.
Alembic owns `public` only and must be configured to ignore that schema, or a
stray autogenerate will try to drop it.

## Static files

```
backend/content/campaigns/<campaign_id>/<version>/
    campaign.json          # metadata + ordered adventure list + seed player character
    adventures/<id>.json   # includes a prose intro and an entry_scene
    scenes/<id>.json       # truth[], npc_intent?, consequences[], hidden[],
                           # creatures[], exits[] (a list, not a map), pressure?
    definitions/<id>.json  # one entity for NPCs and monsters alike; always
                           # carries a stat block
backend/content/srd/        # SRD 5.1 source for the ingest CLI

backend/app/modules/game/prompts/
    system/dm.md
    personality/<id>.md     # the run's personality id references these
    character_generation.md
    adventure_generation.md

/data/media/portraits/<id>.png       # Docker volume, never in git
```

The content root is `backend/content/`, not a repository-root `content/`: the
Dockerfile copies `backend/` and compose bind-mounts it, so the path is
identical in the image, under the dev bind mount and on the host, with no
configuration.

- **Content** is read-only by convention — nothing writes it and the loader
  only reads — and is reviewed as diffs in PRs. NPC prompt fragments belong to
  content, not to the prompts directory; they may move to the database later,
  and nothing outside the content loader may assume a file.
- **Prompts** live in the module that uses them, versioned in git. The dev
  drawer selects known ids and may set a free-text override stored on the run;
  it never edits a file.
- **Portraits** are downloaded once from the image API to the media volume and
  served by a static route, so a save does not break when a provider link
  expires. Only the relative path is stored.

## Lifecycle

| Action | Effect |
|---|---|
| Start a playthrough | Pin the campaign and content version; create the owner member row; instantiate **all** objects the pinned content declares; generate the player's creature |
| Start an adventure | Create an AdventureRun; put the player's creature in the entry scene |
| Archive | The player-facing removal gesture — a status change; nothing is deleted |
| Purge | A Typer CLI command hard-deletes archived runs: cascade across members, adventure runs, objects, encounters, events and journal entries, plus the checkpointer thread and the portrait file |

There is no `DELETE /playthroughs/{id}`. Real removal is an operator action.

## Known gaps

Recorded, not solved:

1. **Party position is undefined for multiplayer.** Position lives on the
   player's creature; two characters can be in different scenes. The first thing
   multiplayer must answer.
2. **A mis-retrieved journal entry can contradict established canon**, because
   situational facts have no deterministic flag store. Accepted trade for
   keeping content declarative.
3. **Content integrity is loader-enforced, not database-enforced.** A typo in a
   scene's exits is caught at load time or not at all.
4. **Object state correctness rests entirely on the per-kind Pydantic models.**
   If one write path bypasses them, the mechanics layer is no longer
   deterministic.
