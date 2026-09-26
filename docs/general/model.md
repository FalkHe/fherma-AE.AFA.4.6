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
- **Authored Campaign- and Adventure-Definitions are static JSON in git**,
  never rows, and so is the Story they carry. Runs reference them by string id
  plus a pinned version.
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
  User ──< campaign_run_members >── campaign_runs ──> campaign_id + content_version
                                        ├──< adventure_runs ──> adventure_id
                                        ├──< objects  (creature, item, fixture)
                                        └──< events   (what happened;
                                              narration rows carry a vector)

KNOWLEDGE
  SrdRule  (pgvector, owned by nobody, built by an ingest CLI)
```

- A **campaign run is one run of one campaign**, not of one adventure. The
  player plays adventure after adventure inside it with the same character, so
  the character, the objects and the narration all hang off the campaign run
  and survive adventure boundaries.
- **Everything under a campaign run cascades from it.** `adventure_runs`,
  `objects` and `events` are owned rows with no independent existence. A run
  that has actually been played is never deleted in normal operation (see
  Lifecycle); the cascades are declared so that referential
  integrity holds if an operator purge ever lands, and so that putting away a
  run abandoned before it ever got a character can remove it, and everything
  under it, in one operation.
- **Campaign is a full domain entity** with a stable id — it just lives in a
  file rather than a table. Campaign-Definition ids carry **no foreign key**;
  their referential integrity is loader-time validation, not a database
  constraint.
- **Definitions are campaign-scoped, not adventure-scoped.** A recurring NPC —
  the patron who hires the party, the villain who escapes in adventure 1 and
  returns in adventure 3 — is the normal shape of a campaign, and a monster
  stat block is reusable anywhere. So a Scene *references* a definition by id;
  it does not own one. This is the Campaign-Definition mirror of objects hanging
  off the campaign run: definition above the adventure, instance above the
  adventure run, and nothing about a returning character is per-adventure.
- **SrdRule belongs to no run.** It is global knowledge, rebuilt by a CLI, and
  survives every playthrough. Entities are named for what they hold, never for
  how it is stored — which is why this is not an `embeddings` table and a row
  is not a "chunk". How a rules section is split for retrieval is a column
  concern.
- One campaign and one adventure ship first. That is the **initial authored
  set, not a ceiling**: more adventures and campaigns arrive as a new content
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

A campaign run names the content revision it started with. Loaders serve exactly
that revision, so editing a scene never mutates a save in progress, and a
campaign extended with a fourth adventure ships as a new version that only new
runs pick up. Existing runs finish what they started — which is why objects can
be instantiated eagerly (below) with no backfill path.

**The mechanism**: a version is a `v<n>` directory under the campaign,
served whole by the loader and never edited in place.

### Settings live on the run

Model, temperature, DM personality and any system-prompt override belong to the
campaign run, so a save replays with the tone it was played at. There is no
user-level settings row and no override chain. Personality is referenced by the
id of a prompt file, never as stored prompt text.

### Ownership lives on the membership row

Ownership is a role on `campaign_run_members`; the campaign run deliberately
carries no owner column, so there is one source of truth and authorisation is a
join. One member row per run today, and the membership table is the model's one
concession to the multiplayer capstone. The count of characters is not a second
concession but a plain consequence: the model lets a user control several
characters in one campaign run; Stage-01 gameplay assumes one, and no constraint
enforces it.

### One generic `objects` table, campaign-scoped

Every interactable thing — the player character, allies, monsters, items,
fixtures — is one row in `objects`, owned by the **campaign run**, so a goblin
that lost an arm in adventure 1 still has one arm in adventure 2. Instance keys
are deterministic and stable across a run, so a Campaign-Definition can name an
instance without a lookup table.

**Kinds are `creature`, `item`, `fixture`.** There is no `npc`/`monster` split:
a monster *is* an NPC, and "monster" only means "ships a stat block and is
usually hostile" — a Campaign-Definition trait, not a storage kind. The player
character is likewise not a kind of its own; it is a creature identified by the
user who owns it. Unlike every other object the content declares, though, it
carries no authored template: it is made when the player creates their
character, not instantiated from one when the run starts.

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
guard. **Those four columns are nullable and are populated for `creature` rows
only** — an item and a fixture carry no hit points and no armour class in the
authored template, so there is nothing to promote and nothing for the mechanics
layer to invent. Abilities, inventory, disposition, injuries and improvised
traits stay in the blob.

Objects are instantiated **eagerly when the run starts**: everything the pinned
content version's templates and placements declare, across all its adventures
— except the player's own creature, which the run does not yet have. No lazy
creation during play, no half-populated scenes.

### A carried object is its own row, pointing at its owner

An object template placement may declare that the instance it creates **carries**
other instances at spawn — the boss holding the key, the sack holding the fleeces.
Each carried instance is **its own `objects` row** with a nullable
self-referencing `owner_object_id` naming the row that holds it; `NULL` means the
object stands free in its scene. The reference cascades with the owner's
deletion, and one level of ownership is all the authored content can express.

A carried instance is not folded into the owner's inventory blob. It is a real
object with the same identity, the same state blob and the same
`update_object` path as any other, so it can be taken, dropped, broken or
targeted without a second mechanism — which is exactly what the one generic
table exists to buy. The authored side of this is `Placement.carries[]`, pinned
in [modules/content.md](../modules/content.md).

### Position

**Position belongs to the creature, not the party**: the pair
`(adventure_run_id, scene_id)` on its own `objects` row. No row claims a party
position — splitting the party is ordinary play, so two creatures may stand in
two scenes, and "who is here" is a query over `objects`, never stored. The
adventure run scopes the scene id, which is unique only inside its adventure
file; the active adventure is the `adventure_runs` row whose status says so.

### Combat

**Deferred to the DM-turn phase; this phase builds no combat state.** There is
no encounter row and no stored initiative order. Hit points and conditions
already live on `objects` rows, so what a fight would add is only what is
transient to it — an ordered participant list, a round counter and a turn
pointer — and that shape is fixed by the phase that builds the turn loop driving
it, not before.

### Situational facts have no flag store

"The alarm was raised", "the village turned hostile" live in the **narration**
that reported them, not in columns. Consequence, accepted deliberately: an
Adventure-Definition **cannot deterministically gate an exit** on a flag,
because no flag exists for code to read. Situational conditions are written as
scene *truth* — Story — and judged by the agent, which matches "facts +
intentions + consequences, not scripts" — and means a narration line that was
true can still come back as a hit after it stopped being true, contained by the
recent turns already in the chat history and by hard canon — hit points,
position, inventory, scene — which lives on objects and is read by tool, never
by search.

### Narration is the memory: one stream, an optional vector

**The DM's long-term memory is its own past narration** — every narration line
is encoded as it is written and searched by meaning across the whole campaign
run, across adventures.

It has to be durable, because campaigns outlive context windows. Chat history
is a window, not storage: it gets summarised, and a summariser discards exactly
the flavour that matters (a nickname the player coined for an NPC).
Adventure-sized state may fit in context; **campaign**-sized state will not.
The narration, though, is already written down, complete and in the adventure's
voice — so the cheapest durable memory is the one the DM produced anyway, made
findable by meaning rather than re-authored as facts.

**Events** are system-written, complete and ordered: narration, player input,
dice rolls, tool calls, errors and token cost in one append-only stream. The
trace panel, roll log and cost display are one ordered query with a filter, and
run cost is a sum over it — there is no denormalised total. Hidden rolls are
written with DM visibility and filtered out on read, so the audit trail survives
even when the player does not see it. Nothing is pruned: events are the evidence
of how the agent behaved.

**A narration event also carries an optional vector** and the name of the model
that encoded it. The column is nullable by design and only narration rows fill
it — rolls, tool calls and errors never enter the index. The vector is produced
inside the single transcript writer, as the line is written: one write path, so
no narration can reach the stream unencoded by taking another route. The
embedding's tokens and cost are booked on that same row, which keeps the price
of remembering inside the run total, like every other model call.

The asymmetry is deliberate: **only the DM's narration is encoded, never the
player's typed text**, which stays verbatim in the timeline. The player's intent
still reaches memory, because narration always acknowledges what the player did,
in the adventure's tone.

There are two reads and no third. `recall(query)` searches the run's past
narration by meaning, on demand, for as long as the session runs. And when a run
resumes as a new chat, the DM is handed the **most recent N narration lines up
front**, by recency — there is no player action yet to match on, so that recap
is given to it, not asked for: it is not a tool.

**An encoding failure never fails a write.** It is logged, the narration is
written and shown as usual, and only that one line is not findable by meaning
later; the player notices nothing. Re-encoding the missed lines is a background
job Stage 02 can add if it turns out to happen often.

*Rejected alternative — a curated journal.* A second table of agent-written
truths, reached by a fact event type and a DM fact-writing tool, buys
classification (a durable naming fact outranking a one-off outcome) and a
smaller, denser index. It costs more than it buys: the DM has to decide
mid-turn what will matter later, and whatever it does not think to write down is
gone for good, while the narration it wrote anyway is free and complete. It also
adds a second write path beside the transcript writer, a second lifecycle to
keep in step with the run, and a store of facts that can disagree with the
narration the player actually read. If a curated journal turns out to be a need,
it is added in Stage 02 on top of this — it is not the ground layer.

### One embedding model, two tables

Narration events and SRD rules share the embedding model, pinned in settings
with the dimension fixed in the migration, so they also share the ingest path,
the similarity operator and the cost line. Each vector row records which model
embedded it, so a re-embed is detectable.

They do **not** share a table, and the two tables are the ones that already
exist: `events` and `srd_rules`. A shared pipeline is not a shared shape: a
narration row is owned by a campaign run, cascades with it, is ordered, and is
read by scan for the timeline as often as by similarity for recall; an SRD rule
is owned by nobody, is replaced wholesale by a re-ingest, and cites a section
and a position within it. *Rejected alternative — one `embeddings` table with a
scope key.* Every column above turns nullable, the foreign key to the campaign
run stops being enforceable, two lifecycles — cascade-with-the-run versus
rebuild-the-corpus — hide behind a discriminator, and the transcript writer
would have to write the vector to a second table instead of onto the very row it
describes.

### The checkpointer is the library's, not ours

LangGraph's `AsyncPostgresSaver` creates its own tables — `checkpoints`,
`checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations` — through its
own `setup()`. The saver has no schema option: the table names it emits are
unqualified, so they land wherever the connection's `search_path` points them.
The connection string used to build the saver sets that `search_path` to a
dedicated **`checkpoints` schema**, which `CREATE SCHEMA IF NOT EXISTS` must
create beforehand — `setup()` does not create the schema itself, only the
tables inside whichever one it is pointed at.

Alembic owns `public` only. It is configured to ignore the checkpointer's
tables deliberately: `include_schemas=True` so autogenerate reflects every
schema including `checkpoints`, paired with an `include_object` predicate that
rejects anything in it. Without both, autogenerate never looks at
`checkpoints` in the first place, and the exclusion is incidental rather than
enforced — a stray autogenerate could still try to drop it.

## Static files

```
backend/content/campaigns/<campaign_id>/<version>/
    campaign.json          # metadata + ordered adventure list + seed player
                           # character + object_templates[]: the campaign-scoped
                           # creature / item / fixture blueprints
    adventures/<id>.json   # the adventure and its scenes inline: a prose intro,
                           # an entry_scene, and scenes[] carrying truth[],
                           # npc_intent?, consequences[], hidden[], placements[],
                           # exits[] (a list, not a map), pressure?
backend/content/srd/        # SRD 5.1 source for the ingest CLI

backend/app/modules/<capability>/prompts/v<n>/<kind>/<id>.md
    # e.g. modules/game/prompts/v1/decision/read-move.md
    #      modules/game/prompts/v1/narration/beat.md
    # each capability owns its own prompts/ tree; there is no shared root, so a
    # character-generation prompt lives under whichever capability owns that
    # agent, never nested inside `game`

/data/media/portraits/<id>.png       # Docker volume, never in git
```

The content root is `backend/content/`, not a repository-root `content/`: the
Dockerfile copies `backend/` and compose bind-mounts it, so the path is
identical in the image, under the dev bind mount and on the host, with no
configuration.

**There are exactly two kinds of file, and no `scenes/` or `definitions/`
directory.** A scene belongs to exactly one adventure, so it lives inside that
adventure's file; an object template is campaign-scoped and shared between
adventures, so it lives in the campaign-scoped file.

- **Campaign- and Adventure-Definitions** are read-only by convention —
  nothing writes them and the loader only reads — and are reviewed as diffs in
  PRs. NPC prose fragments are Story and belong to the Campaign-Definition, not
  to the prompts directory; they may move to the database later, and nothing
  outside the content loader may assume a file.
- **Prompts** live under the capability that uses them, versioned in git, and
  an id resolves against its **owning capability's own prompt directory** —
  never a shared root. An id is three lowercase-kebab segments,
  `<capability>/<kind>/<id>`; resolution serves the highest `v<n>` present
  unless a specific version is named, and the id grammar admits nothing but
  well-formed segments, so a malformed or path-escaping id is refused outright
  rather than resolved to a nearby file. A prompt file is plain Markdown with
  no frontmatter — the resolver serves its text verbatim. The dev drawer
  selects known ids and may set a free-text override stored on the run; it
  never edits a file.
- **Portraits** are downloaded once from the image API to the media volume and
  served by a static route, so a save does not break when a provider link
  expires. Only the relative path is stored.

## Lifecycle

Built across Phase 5 — Game State Services. Starting a run, giving it its
character and putting it away already run today; entering an adventure and
moving a run into active play remain later steps of the same phase.

| Action | Effect |
|---|---|
| Start a campaign run | Pin the campaign and content version; create the owner member row; instantiate every object the pinned Campaign-Definition declares, other than the player's own creature — the run exists and its world is in place, but it has no character yet |
| Create the character | Build the player's creature from the seed player character, carrying its starting equipment as real objects of its own; the run now has its one character and moves on from freshly started |
| Start an adventure | Create an `adventure_runs` row; place that adventure's cast — the player's creature among them — in the scenes the content puts them in |
| The first narration | Moves a run with a character into active play — the step exists already, but nothing yet triggers it; a later phase wires it in |
| Archive | Puts a run away, subject to the shelf life below |

A run that has reached a character, active play or a finished story can be
archived. There is no way back: an archived run is kept only so its story can
be read again, never played on further, and every write to it is refused —
though it still lists among the player's runs and still reads. A run archived
before it ever got a character is different: it was never really played, so
archiving it at that point deletes it outright — the run, its membership and
everything instantiated for it — and the player is not asked twice.

**Nothing else is ever deleted**: for a run that reached a character or
beyond, archiving is a status change, there is no delete route and no purge
command, so the event stream and the cost record it carries survive a run the
player has put away.

## Known gaps

Recorded, not solved:

1. **A narration line that was true can still come back as a hit after it
   stopped being true**, because situational facts have no deterministic flag
   store. Contained by the recent turns already in the chat history and by hard
   canon — hit points, position, inventory, scene — which lives on objects and
   is read by tool, never by search. Accepted trade for keeping the
   Adventure-Definition declarative.
2. **Campaign-Definition integrity is loader-enforced, not database-enforced.**
   A typo in a scene's exits is caught at load time or not at all.
3. **Object state correctness rests entirely on the per-kind Pydantic models.**
   If one write path bypasses them, the mechanics layer is no longer
   deterministic.
