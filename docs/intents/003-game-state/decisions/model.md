---
author: fhit:architect
owner: human
created: 2026-09-16
updated: 2026-09-16
stage: draft
---
# Attachment: the game-state schema

A proposal for approval. Five tables, one module, one migration. Bound by D1–D13; where a decision forced a
shape it is named inline. Anything invented without a decision behind it is marked **ASSUMPTION** and
numbered 1–15 — those are the lines to veto.

**D2 is applied literally:** the two state entities are `campaign_run` and `adventure_run`, and **no table,
column, class or schema below is called "playthrough"**. The word appears only as **D14**'s module name and as
ordinary prose for the activity — the module is where a playthrough happens.

## 1. The shape

A campaign is a grouping and cannot be played; an adventure is what gets played (**D10**). So:

- **`campaign_runs`** — the container. Ownership, the content-version pin, the title, settings, status, and
  everything that must survive an adventure boundary: the objects and the event stream hang off it.
- **`adventure_runs`** — one adventure being played. One row per adventure **entered**, recording which
  adventure, when it was entered, and whether it is done.

Objects and events stay at campaign-run level (**D10**): a character and its inventory carry across
adventures (a goblin that lost an arm in adventure 1 still has one arm in adventure 2), and **D5** makes the
visible event stream the transcript — one continuous thread, so splitting it per adventure would break
resume at every boundary.

**Position belongs to the creature, never to the party (D12).** Splitting the party is normal play and the
DM cuts between groups, so two characters may stand in two scenes. No row in this schema claims a party
position. **A user may control several characters in one campaign run (D13)**, and nothing below restricts
the count; Stage-01 *gameplay* ships one.

```
users ──< campaign_run_members >── campaign_runs ──< adventure_runs
 (auth)          role='owner'            │   pin: campaign_id + content_version (D7)
       one member row per user           │   title, nullable (D11)
       per campaign run                  │   status: active|archived|finished (D3)
                │                        │   4 override columns, all NULL (D6)
                │                        │        │  adventure_id, status: active|completed
                │                        │        │  started_at / completed_at
                │                        │        └  at most one active per campaign run
                │                        │                      ▲
                │                        ├──< objects ──────────┘  position = (adventure_run_id, scene_id)
                └────────────────────────┼──────┘ member_id: whose character this is (D13, 0..n per member)
                                         │        owner_object_id → objects (carried things)
                                         │
                                         └──< events   append-only, ULID-ordered, visibility player|dm (D4),
                                                       cost per event (D4), actor_member_id
```

**Not built here:** no encounter and no initiative (**D8**), no journal (phase 6), no SRD table (phase 4),
no turn-taking and no spotlight of any kind.

## 2. Where this lives: one module, and its name

### 2.1 Does state live apart from the gameplay that changes it? (D14)

**No. One module owns the five tables and phase 5's transitions over them.** The argument is this
codebase's, not taste.

**The project already made this split once, and it is not state-versus-behaviour.** `users` owns the person
record *and* the services that write it; `auth` owns the session lifecycle *and* the `sessions` table, and
calls `users.service` in one direction (`backend/app/modules/users/README.md`,
`.../auth/README.md`). `content` owns a whole capability with **no table and no route at all**
(`.../content/README.md`). The precedent is: **a module is a capability, and a capability owns its own rows
plus the code that writes them.** No module in this tree holds tables that a different module writes.

**A state-only module would be a layer, and layers are ruled out by name.** `AGENTS.md` and
`docs/general/architecture.md:101` say both trees are organised by domain module, *not* by technical layer.
"Tables here, the things that change them there" is the definition of a technical layer.

**It would also break two other rules at once.** Services own the transaction boundary and routes contain no
`commit`; so if the transitions lived outside the module that owns the rows, either (a) the table-owning
module exposes generic `update_object(...)` / `append(...)` write functions for somebody else to orchestrate
— a repository class with the word "class" removed, which the same section forbids — or (b) the transition
module imports another module's `models.py` and commits against it, putting one transaction across a module
edge.
The only clean version of (b) would be promoting the session-and-commit dance into `core/`, which the
promotion rule forbids until a **second** module needs it unchanged.

**And the cost is concrete, not theoretical.** Every single turn writes across the tables in one commit:
advancing on an exit moves an `objects` row, may flip an `adventure_runs` row to `completed`, and appends
one or more `events` — with the roll and its cost among them. A hidden roll is one transaction that touches
`objects` and `events` and must not half-commit. This is the common path, not an edge case, so a module edge
through the middle of it would be crossed thousands of times.

**What one module costs, stated plainly:** it will be the largest module in the tree — five tables, the run
lifecycle, the validated object write path, scene advancing, the event append with visibility and cost, and
dice inside the transition that records the roll. That is a real review surface. The mitigation is internal:
one `service.py` per concern inside the module if it grows (`service/objects.py`, `service/events.py`), which
keeps the transaction boundary intact because the module edge is where it always was.

### 2.2 What happens to `modules/game/`

**It stays, and it stays separate.** It holds `prompts/v1/system/` today and it is the agent's home: the
LangGraph loop, the guard node, the tool bindings, the prompts. That boundary is `AGENTS.md`'s own rule —
content, reasoning and mechanics stay separate, and the LLM never edits state directly, it calls a tool. The
tool implementation calls `playthrough`'s `service.py`, which is exactly the permitted cross-module edge.
Absorbing `game` would merge reasoning into mechanics; moving tables into `game` would put the agent's
module in charge of the rows it is not allowed to touch directly.

**The one allowed import direction (D14):** `game` → `playthrough`'s `service.py`, never the reverse —
`playthrough` knows nothing about agents. `playthrough` itself reads `content.service` (the loader) for
instantiation and for the scene validation of §3.1, the same one-way edge `auth` → `users` already uses.

### 2.3 The name (D14)

**`backend/app/modules/playthrough/`** — `models.py`, `schemas.py`, `service.py`, `routes.py`, mirrored by
`backend/tests/playthrough/`. **One sentence for what belongs in it:** everything that exists only because
somebody is playing — the campaign run and its members, the adventures entered, the objects, the event
stream, and every transition that changes them — but not the authored material they are made from
(`content`) and not the agent that decides what happens (`game`).

The name is right precisely because a *playthrough* is the activity, not an entity: **D2** forbids it as the
name of a state entity, because a campaign is a grouping that cannot be played, and nothing below is called
that. As a module name it says what happens inside. Chosen over `play` and `gameplay`, and over
`campaign_run` (which takes `content`'s word `campaign`), `session` (already an auth session here) and
`state` / `store` (layer names, §2.1).

One line joins the existing two in `backend/alembic/env.py`: `from app.modules.playthrough import models`.

**Conventions carried over, not re-invented.** Every id and foreign key is `ID_TYPE` (`CHAR(26)`) with
`default=generate_id` (`app/core/ids.py:12`-`17`). Constraint names come from the naming convention in
`app/core/db.py:19`-`25`; composite constraints get their name spelled out in the migration, because the
convention names from the *first* column only. Timestamps are `TIMESTAMP WITH TIME ZONE` with
`server_default now()`, following `users.created_at`. Cascades follow the `sessions.user_id` precedent
(`app/modules/auth/models.py:17`-`19`).

**ASSUMPTION 1 — enums are `VARCHAR` + a `CHECK`, not Postgres `ENUM` types.** A native enum needs its own
`ALTER TYPE` in a migration to gain a value, and phase 8 is likely to add event types. A check constraint is
dropped and recreated, and reads identically in psql. No enum exists in the codebase today, so this sets the
precedent.

**ASSUMPTION 2 — `DELETE` cascades are declared even though D3 says nothing is ever deleted.** Referential
hygiene, not a feature: no route, service or CLI in this phase deletes anything. If an operator purge ever
lands, the cascade is already correct.

## 3. The questions the decisions force

### 3.1 Position: the concrete shape, and what enforces it (D12)

**A creature's position is the pair `(adventure_run_id, scene_id)` on its own `objects` row.** The scene id
is scoped by the adventure run it points at, which is what makes it meaningful — a scene id is unique only
inside its adventure file (scenes live inline in `adventures/<id>.json`, and nothing makes the ids globally
unique), and `adventure_runs.adventure_id` names that file. The pair resolves by one join, and no position
is hoisted to the party.

Position is kept separate from **provenance**, because the two are different facts and eager instantiation
makes them differ in time:

| Columns | Meaning | Written |
|---|---|---|
| `source_adventure_id`, `source_scene_id` | which authored placement produced this row | once, at instantiation; never changed |
| `adventure_run_id`, `scene_id` | where it stands right now | when the adventure is entered, then on every move |

Objects are instantiated eagerly for **every** adventure the pinned version declares, so a row for adventure
two exists before adventure two has been entered and before its `adventure_runs` row exists. That row simply
has no position yet: both position columns are NULL until entry, at which point placing the adventure's cast
is one statement — `UPDATE objects SET adventure_run_id = :ar, scene_id = source_scene_id WHERE
campaign_run_id = :cr AND source_adventure_id = :adv`. Creation stays eager, as `model.md` requires; only
placement waits for the adventure to exist.

**What enforces that the scene belongs to the adventure the position points at.** Three layers, and the
honest limit is named:

1. `ck_objects_position` — `adventure_run_id` and `scene_id` are both NULL or both set. A scene id can never
   float without the adventure run that scopes it.
2. The FK on `adventure_run_id` makes the adventure identity unforgeable: the pair always reads as
   (that adventure run's `adventure_id`, this scene id).
3. **Whether that scene id exists inside that adventure file is loader-validated at write time, not
   database-enforced** — the move path resolves the scene through `load_campaign(...)` for the run's pinned
   version and refuses an unknown id. That matches the project's standing rule: content ids carry no foreign
   key, integrity is loader-time (`model.md:47`), and `backend/app/modules/content/service.py:319`
   (`load_scene`) is already the function that does it. A database cannot check membership of a JSON file;
   claiming otherwise would be theatre.

*Rejected:* denormalising `adventure_id` back onto the object and adding a composite FK
`(adventure_run_id, adventure_id) → adventure_runs(id, adventure_id)`. It guarantees only what layer 2
already guarantees and leaves the actual gap — scene membership — where it is, at the price of a redundant
column that can go stale.

### 3.2 What `adventure_runs` holds, and whether it earns its place

It does, on three counts, and only the third is about position:

1. **Progress across a multi-adventure campaign (D10).** Which adventures have been entered, when, and
   which are done. That history exists nowhere else, and `campaign.adventures[]` can grow.
2. **The active adventure.** Derived from `status = 'active'`, enforced to be at most one per campaign run
   (§3.4). It is what a resumed turn needs before it can read anything about the world.
3. **The scope that makes a scene id meaningful (§3.1).** Every position in the system points at it.

It holds no position of its own and makes no claim about where "the party" is.

### 3.3 How "the party" is expressed

**It is not an entity. "Who is in this scene" is one query with no special case:**

```sql
SELECT * FROM objects WHERE adventure_run_id = :ar AND scene_id = :scene
```

Player characters, NPCs, monsters and fixtures all answer it the same way (§3.5). "The party at this moment"
is *the creatures sharing a scene* — a derived set, computed per query, never stored. A split party is two
such sets and needs no extra state.

**There is no spotlight column and no current-focus pointer.** Which group the DM is narrating when a party
is split is a DM-turn judgement, and phase 8 owns it — the same ground on which **D8** defers combat. A
column that nothing writes and nothing reads is a guess, not readiness; D6's override columns are different
because a decision points at them.

### 3.4 Campaign-run status, and the active adventure

The campaign run's status and its adventure runs' statuses are **independent columns with no schema
relationship**: "the last adventure completed ⇒ the campaign run is `finished`" needs
`campaign.adventures[]`, which lives in a JSON file the database cannot read, so enforcement would be a
trigger encoding content knowledge in SQL. **D3** defines `finished` as a judgement about the campaign, and
phase 5 owns the run lifecycle. Archiving is orthogonal in both directions.

`current_adventure_id` does **not** exist on the campaign run: a pointer plus a status is two sources of
truth that can disagree. The active adventure is the one with `status = 'active'`, enforced by a partial
unique index — `CREATE UNIQUE INDEX uq_adventure_runs_active ON adventure_runs (campaign_run_id) WHERE
status = 'active'`. The trade-off: "which adventure now" is a one-row query rather than a column read, and
the index is Postgres-specific, which this project already is.

### 3.5 NPCs, monsters, fixtures — and carried items

**They carry position identically** — the same `(adventure_run_id, scene_id)` pair on the same table. That
uniformity is the point of one generic `objects` table, and after **D12** there is no row whose position is
stored anywhere else.

**A carried item has no position of its own.** It carries `owner_object_id` and both position columns NULL;
where it is, is where its holder is, one join away.

**ASSUMPTION 3 — `ck_objects_location`.** Two clauses: `adventure_run_id` and `scene_id` are both NULL or
both set; and if `owner_object_id IS NOT NULL` then both position columns are NULL. A row with no owner and
no position is legal and means exactly one thing — it belongs to an adventure nobody has entered yet. Veto
it if an object should be able to be both carried and standing somewhere.

### 3.6 Several players, and several characters per player (D12, D13)

`campaign_run_members` already allows several members per campaign run, and **D13** allows a member to
control several characters. The schema therefore says nothing about how many characters anyone has.

**What identifies a player character:** an `objects` row with `kind = 'creature'` and `member_id` set. The
link to the human is `member_id` → `campaign_run_members` → `users` — through the membership row, never a
`user_id` on the object, because ownership already lives on the membership row (`model.md`) and one path
beats two that can disagree.

**What identifies *the* player's character: nothing, and that is the honest position.** There is no unique
index, so "the player's character" is a *gameplay* assumption of Stage-01 (**D13**), not a fact the database
will defend. Concretely, if a second character for one member ever appeared:

- Every read written as "the member's character" — the character sheet, the object the DM narrates for, the
  position the adventure-completion rule looks at (§3.7), phase 7's portrait and generation step — would
  match two rows. Written naively (`.first()`) they would silently pick one, which is worse than failing.
- Nothing in the *data* would be corrupt: two characters is a legal state, both positioned, both alive,
  both attributable through their member row. The damage would be entirely in code that assumed one.

**The remedy belongs to phase 5, and I recommend it explicitly:** the service helper that resolves a
member's character raises a domain error when it finds more than one, so the assumption fails loudly at the
seam that holds it rather than silently in a screen. That is a service rule, not a constraint, because
**D13** says the schema must not restrict the count.

**Attributable actions** — `events.actor_member_id`, nullable, FK to `campaign_run_members`. **D4**'s stream
includes the player's own actions; with two players, or one player and two characters, a transcript that
cannot say who acted is a hole in the audit trail the brief asks for. NULL on narration, rolls, tool calls
and system events. **ASSUMPTION 13.**

**What multi-player readiness explicitly does *not* require here:** no party or group entity; no
turn-taking, initiative or spotlight (**D8**, §3.3); no per-member settings — **D6** keeps settings on the
campaign run; no shared inventory — items are objects with an owner; no invite or join flow, which is a
route and a later concern, not a table.

**ASSUMPTION 15 — `role` keeps its single value `'owner'`.** A second value (`'player'`) is a one-line
`CHECK` swap, and until a join flow exists nothing would ever write it. A value no code writes is a value
somebody later has to interpret.

### 3.7 What "this adventure is done" means

**ASSUMPTION 4 — completion is a recorded fact, and the rule that writes it is positional only while there
is one character.** The only structural end signal the content carries is a scene with no exits:
`Scene.exits` is a plain list that may be empty (`content/schemas.py:104`), and the authored adventure ends
exactly that way (`lair-hollow` has zero exits; the other three scenes have one each). There is no `ending`
flag and no terminal marker in the content schema.

With the one character Stage-01 gameplay assumes (**D13**), the smallest honest rule is: **the adventure run
is `completed` when, at the end of a turn, that character stands in a scene with no exits.** With characters
apart (**D12**) the rule stops being obvious in a way no decision resolves — one character reaching the last
room while another is three scenes back is a signal, not a conclusion, and the sensible generalisations
(every character, or the DM declaring it) are both DM-turn judgements. The **generalisation is deferred to
phase 8**, on the ground **D8** already uses, and what this phase fixes is only that the fact and its
timestamp are recorded. If you would rather the content declare its ending explicitly, that is a phase-1
schema change (`Adventure.ending_scene`), not a change here.

**ASSUMPTION 5 — the status value set** stays `active | completed`. No `abandoned` or `failed`: the authored
content has no failure state, adventures play in the order `campaign.adventures[]` declares, and a value
nothing writes is a value somebody later has to interpret. Adding one is a `CHECK` swap.

**ASSUMPTION 6 — one row per adventure, entered at most once**, enforced by `UNIQUE (campaign_run_id,
adventure_id)`. This is **D10**'s "one row per adventure entered" read strictly; re-entering a finished
adventure is not something the content can express today. The cost of being wrong: replaying an adventure
needs the constraint dropped or an attempt ordinal added.

## 4. Tables

### 4.1 `campaign_runs`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `CHAR(26)` | no | PK `pk_campaign_runs`, `default=generate_id` |
| `campaign_id` | `VARCHAR(64)` | no | content id; **no FK** — campaigns are files, integrity is loader-time (`model.md:47`) |
| `content_version` | `VARCHAR(16)` | no | the pinned `v<n>` directory. **D7**: never shown to the player, kept for the run's life |
| `title` | `VARCHAR(120)` | **yes** | **D11** — empty means the list shows campaign name + creation date; the owner may set one at any time |
| `status` | `VARCHAR(16)` | no | `default 'active'`; **D3** → `CHECK status IN ('active','archived','finished')`, `ck_campaign_runs_status` |
| `model` | `VARCHAR(64)` | yes | **D6** — NULL in Stage-01, falls back to `Settings.chat_model` |
| `temperature` | `NUMERIC(3,2)` | yes | **D6** |
| `personality_prompt_id` | `VARCHAR(128)` | yes | **D6** — a prompt id, never prompt text |
| `system_prompt_override` | `TEXT` | yes | **D6** |
| `created_at` | `TIMESTAMPTZ` | no | `server_default now()`. D11's fallback label reads this |
| `updated_at` | `TIMESTAMPTZ` | no | `server_default now()`, `onupdate now()` |

Indexes: none beyond the PK — the list query arrives through `campaign_run_members`, which carries it.

- **D1** is satisfied by the *absence* of a unique constraint on `(user, campaign_id)`. Nothing is added; the
  point is that nothing may be added later without overturning D1.
- **ASSUMPTION 7 — no `archived_at` / `finished_at`.** `updated_at` carries "when did this last change", and
  nothing in Stage-01 reports on *when* a run was archived. Both are additive nullable columns later.

### 4.2 `campaign_run_members`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `CHAR(26)` | no | PK `pk_campaign_run_members` |
| `campaign_run_id` | `CHAR(26)` | no | FK → `campaign_runs.id`, `ON DELETE CASCADE` |
| `user_id` | `CHAR(26)` | no | FK → `users.id`, `ON DELETE CASCADE` — the `sessions.user_id` precedent |
| `role` | `VARCHAR(16)` | no | `default 'owner'`; `CHECK role IN ('owner')` — **ASSUMPTION 15** |
| `created_at` | `TIMESTAMPTZ` | no | |

- Unique `(campaign_run_id, user_id)` → `uq_campaign_run_members_campaign_run_id`, named explicitly. **One
  membership row per user per campaign run** — which is not a limit on characters (**D13**); characters hang
  off this row, and there may be several.
- Index `ix_campaign_run_members_user_id` — "my runs" and every authorisation check, so it is the one index
  the app leans on.
- The ownership root: `campaign_runs` deliberately carries **no owner column**, so authorisation has one
  source of truth and is a join.

### 4.3 `adventure_runs`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `CHAR(26)` | no | PK `pk_adventure_runs` |
| `campaign_run_id` | `CHAR(26)` | no | FK → `campaign_runs.id`, `ON DELETE CASCADE` |
| `adventure_id` | `VARCHAR(64)` | no | content id from `campaign.adventures[]`; no FK (content is files) |
| `status` | `VARCHAR(16)` | no | `default 'active'`; `CHECK status IN ('active','completed')`, `ck_adventure_runs_status` (§3.7) |
| `started_at` | `TIMESTAMPTZ` | no | `server_default now()` |
| `completed_at` | `TIMESTAMPTZ` | yes | set with `status = 'completed'` |
| `updated_at` | `TIMESTAMPTZ` | no | `server_default now()`, `onupdate now()` |

- **No scene column**: positions live on the creatures that hold them (**D12**, §3.1).
- Unique `(campaign_run_id, adventure_id)` → `uq_adventure_runs_campaign_run_id` (ASSUMPTION 6).
- Partial unique index `uq_adventure_runs_active` on `(campaign_run_id) WHERE status = 'active'` (§3.4).
- `ck_adventure_runs_completed_at`: `completed_at IS NOT NULL` exactly when `status = 'completed'`.
- No index on `adventure_id`: a campaign run has a handful of these rows and every read is already scoped by
  `campaign_run_id`.

### 4.4 `objects`

Every interactable thing — player characters, NPCs, monsters, items, fixtures — is one row, owned by the
**campaign run** (**D10**), so state carries across adventure boundaries. About 14 rows are written when a
campaign run starts, from one `load_campaign()` call: 13 authored placements (3 of them carried) plus the
player character Stage-01 creates.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `CHAR(26)` | no | PK `pk_objects` |
| `campaign_run_id` | `CHAR(26)` | no | FK → `campaign_runs.id`, `ON DELETE CASCADE` |
| `member_id` | `CHAR(26)` | yes | FK → `campaign_run_members.id`, `ON DELETE CASCADE`. Set on a player character and nothing else — this is what makes a creature a PC, and the only link to the human (§3.6). **No unique index: a member may hold several (D13)** |
| `kind` | `VARCHAR(16)` | no | `CHECK kind IN ('creature','item','fixture')` — the authored discriminator (`content/schemas.py:67`-`70`) |
| `template_id` | `VARCHAR(64)` | no | the `object_templates[]` id it was instantiated from; no FK (content is files) |
| `instance_key` | `VARCHAR(160)` | no | deterministic, stable for the run's life (below) |
| `name` | `VARCHAR(120)` | no | copied from the template at instantiation |
| `source_adventure_id` | `VARCHAR(64)` | yes | **provenance**: which adventure's placements produced this row. A content id, deliberately not an FK to `adventure_runs` — objects exist before the adventure is entered (§3.1). NULL for a player character, which belongs to the campaign |
| `source_scene_id` | `VARCHAR(64)` | yes | **provenance**: the authored placement's scene. NULL for a player character and for a carried instance |
| `adventure_run_id` | `CHAR(26)` | yes | **position, part 1** — FK → `adventure_runs.id`, `ON DELETE SET NULL`. Scopes the scene id (§3.1) |
| `scene_id` | `VARCHAR(64)` | yes | **position, part 2** — where it stands inside that adventure run (**D12**) |
| `owner_object_id` | `CHAR(26)` | yes | FK → `objects.id`, `ON DELETE CASCADE`, self-referencing. Set = carried, and then it has no position of its own (§3.5). One level, which is all `Placement.carries[]` can express |
| `current_hp` | `INTEGER` | yes | creature rows only |
| `max_hp` | `INTEGER` | yes | creature rows only |
| `armour_class` | `INTEGER` | yes | creature rows only |
| `is_alive` | `BOOLEAN` | yes | creature rows only |
| `state` | `JSONB` | no | `server_default '{}'`. Abilities, inventory, disposition, conditions, injuries. Written only after validation by the Pydantic model selected by `kind`, and **reassigned whole** — an in-place dict mutation is invisible to SQLAlchemy's unit of work |
| `created_at` / `updated_at` | `TIMESTAMPTZ` | no | |

Constraints and indexes:

- Unique `(campaign_run_id, instance_key)` → `uq_objects_campaign_run_id`.
- `ix_objects_campaign_run_id`; **`(adventure_run_id, scene_id)` → `ix_objects_adventure_run_id_scene_id`**,
  which is the "who is in this scene" query of §3.3 and the hottest read in the game;
  `ix_objects_member_id` (plain, **not unique** — D13) for "this member's characters";
  `ix_objects_owner_object_id` for "what is this carrying".
- `ck_objects_stats_creature_only`: the four promoted stats are all NULL unless `kind = 'creature'`, and all
  NOT NULL when it is. Items and fixtures carry no hit points in the authored templates
  (`content/schemas.py:50`,`:62`), so there is nothing for the mechanics layer to invent.
- `ck_objects_hp_range`: `current_hp BETWEEN 0 AND max_hp`. This is the constraint the promotion exists for.
- `ck_objects_position` and the carried rule: **ASSUMPTION 3**, stated in §3.5.
- **ASSUMPTION 8 — `is_alive` is stored, not `current_hp > 0`.** A creature stable at 0 hit points is not
  dead in 5e, and later phases should be able to say so without inventing a rule at read time.
- **ASSUMPTION 9 — `instance_key` format.** `<source_adventure_id>:<source_scene_id>:<template_id>:<ordinal>`
  for a placement (ordinal `1..count`, so `count: 3` yields three keys) and
  `<owner_key>/<template_id>:<ordinal>` for a carried instance — both derived from authored content, so the
  same content always produces the same keys and a future Campaign-Definition can name an instance without a
  lookup table. **A player character has no authored placement, so nothing content-derived can identify it**:
  its key is `pc:<member_id>:<n>`, `n` counting that member's characters from 1 — which stays unique now that
  a member may hold several (**D13**). Uniqueness is carried by `uq_objects_campaign_run_id` either way.
- **ASSUMPTION 10 — `name` is copied onto the row** rather than read from the template each time. It is what
  a list, a log line and a tool result all need, and an agent renaming an NPC mid-run should stick.

### 4.5 `events`

The append-only record of what happened, owned by the campaign run (**D10**). **D5** makes this table the
transcript: resuming is reloading the page and replaying this stream as it stands, so nothing else stores
where the story got to.

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | `CHAR(26)` | no | PK `pk_events`. ULIDs are time-sortable, so **the id is the ordering** — no sequence column |
| `campaign_run_id` | `CHAR(26)` | no | FK → `campaign_runs.id`, `ON DELETE CASCADE` |
| `actor_member_id` | `CHAR(26)` | yes | FK → `campaign_run_members.id`, `ON DELETE SET NULL`. Who acted; NULL for narration, rolls, tool calls and system events. **ASSUMPTION 13** (§3.6) |
| `turn_id` | `CHAR(26)` | yes | groups every event of one player turn, so a per-turn cost is a `GROUP BY`. NULL outside a turn (run start, adventure boundary) |
| `type` | `VARCHAR(32)` | no | `CHECK type IN ('narration','player_action','roll','tool_call','error')` |
| `visibility` | `VARCHAR(8)` | no | `CHECK visibility IN ('player','dm')`. **D4** — hidden events are written with `dm` and filtered on read; the audit trail survives though the player never sees it |
| `payload` | `JSONB` | no | the body: narration text, the action, the dice expression and result, the tool call and its arguments |
| `prompt_tokens` | `INTEGER` | yes | **D4** — recorded per event |
| `completion_tokens` | `INTEGER` | yes | **D4** |
| `cost_usd` | `NUMERIC(12,6)` | yes | **D4** — the provider's own figure, which `core/llm/service.py` already returns per call. `NUMERIC`, not float, so a `SUM` over a campaign is exact. Reportable to the owner, **never rendered to the player** — an API and UI rule, not a column |
| `created_at` | `TIMESTAMPTZ` | no | wall-clock, for display; ordering still comes from `id` |

Indexes:

- `(campaign_run_id, visibility, id)` → `ix_events_campaign_run_id_visibility_id`. This is **D4 + D5 in one
  line**: the transcript is `WHERE campaign_run_id = ? AND visibility = 'player' ORDER BY id`, and hidden
  rows are skipped by the index rather than fetched and dropped — which is also why they leave no visible
  gap.
- `(campaign_run_id, turn_id)` → `ix_events_campaign_run_id_turn_id`, for the per-turn cost roll-up.
- No denormalised total anywhere: a run's cost is `SUM(cost_usd)` over its rows (**D4**).
- **ASSUMPTION 11 — no `adventure_run_id` on an event.** **D5** makes the stream one continuous thread, and
  an adventure boundary is itself an event in it. Adding the column later is additive and nullable; adding it
  now would invite a per-adventure transcript that D5 rules out.
- **ASSUMPTION 12 — the five `type` values.** They cover everything Stage-01 writes; phase 8 will likely add
  one (a guard rejection, an `ask_player` interrupt), which is a one-line `CHECK` swap.
- **ASSUMPTION 14 — `payload` is free-form JSONB**, not a typed column per type: one shape per event type is
  validated in the service, the same way object state is.

## 5. Migration

The five tables land in dependency order — `campaign_runs` → `campaign_run_members` → `adventure_runs` →
`objects` → `events` — across **four additive revisions beginning at `0003`, `down_revision = "0002"`** (SRD's
`0002_srd_rules` holds `0002`), one per table-carrying sprint, each dropping its own tables in reverse. Every foreign key
resolves in that order: `objects` references `campaign_runs`, `campaign_run_members`, `adventure_runs` and
itself; `events` references `campaign_runs` and `campaign_run_members`. **No table references a later one**, so
there is no cycle, no deferred constraint to add afterwards, and no sprint edits an earlier sprint's revision.

**D9 as amended by D15**: `alembic upgrade head` against the dev database is still what proves a table, but
the proof is no longer hand-run once. The scratch-database fixture SRD shipped
(`backend/tests/srd/conftest.py`) is **promoted to a shared fixture** — a second module now needs it
unchanged, which is this project's promotion rule — and every accept/refuse statement in §§3–4 runs as a
`@pytest.mark.database` test under `make backend-test-db`. `make backend-test` stays `--no-deps` and green:
those tests skip when no Postgres answers. `downgrade()` is written and exercised the same way.

## 6. What D15 makes provable, and what this phase still does not answer

**Newly provable here, rather than in phase 5:** that the migration chain applies and reverses on an empty
database; that every `CHECK` and unique constraint in §4 actually rejects what it claims to
(creature-only stats, the hit-point range, the position/carried rule, one active adventure per campaign run,
completed-with-a-time, the five event types, both visibilities); that a cascade removes what it should and
`ON DELETE SET NULL` leaves the row standing; and that the player-visible event read filters `dm` rows out
while they remain in the table. None of that needed a service, and all of it was going to be taken on trust.

Still not answered here:

- Every write path: services, routes, validation, the object write path and the run lifecycle are phase 5 —
  including who writes `adventure_runs.status`, when a campaign run becomes `finished` (§3.4), the
  loader-time scene validation of §3.1 layer 3, and the helper that resolves a member's character and
  **raises rather than guessing when it finds more than one** (§3.6).
- What a fight is (**D8**) — no encounter, no initiative, no turn order — and with it, how a split party's
  narration focus moves (§3.3) and how adventure completion generalises to several characters (§3.7).
- The per-kind Pydantic models that guard `state` are named here as the rule; they are written where the
  write path is.

## 7. Doc corrections this forces

A work item for the sprint, not edits made here. Every line below is a place where a `docs/` file contradicts
D1–D14 as of today. **Nineteen items across seven files.**

**Vocabulary (D2, D14).** `Playthrough` is the *entity* name in the general docs and must become
`campaign_run` / `campaign run`; `PlaythroughMember` becomes `campaign_run_members`. The word stays legal as
prose for the activity and as the module name — so `model.md:60`, `:81` and `architecture.md:45` need
reading, not blanket replacement.

| # | File:line | What contradicts | Decision |
|---|---|---|---|
| 1 | `general/model.md:30`-`:32` | entity diagram: `Playthrough`, `PlaythroughMember`, `Encounter` under `AdventureRun` | D2, D8, D10 |
| 2 | `general/model.md:41`-`:47` | "A **Playthrough** is one run of one campaign"; "Encounter hangs off AdventureRun" | D2, D8 |
| 3 | `general/model.md:81` | "A playthrough names the content revision" — entity use | D2 |
| 4 | `general/model.md:93` | settings "belong to the Playthrough" | D2 |
| 5 | `general/model.md:97`-`:102` | "Ownership is a role on `PlaythroughMember`" — upheld in substance, renamed; **"one character per member" is now wrong** | D2, D13 |
| 6 | `general/model.md:107` | `objects` "owned by the **Playthrough**" | D2 |
| 7 | `general/model.md:161`-`:163` | **Position**: "the player's creature holds the scene … and that is the party's position" — D12 upholds the creature, **denies the party reading**, and the scene id must be scoped by the adventure run (§3.1) | D12 |
| 8 | `general/model.md:167`-`:171` | the **Combat** paragraph and its Encounter shape | D8 (deferred, not deleted) |
| 9 | `general/model.md:219`,`:223` | journal entry "owned by a playthrough" (phase 6's table, this phase's word) | D2 |
| 10 | `general/model.md:301`-`:302` | lifecycle rows "Start a playthrough" / "Start an adventure … put the player's creature in the entry scene" | D2, D12 |
| 11 | `general/model.md:304` | the **Purge** row — out of Stage-01 scope, and D3 deletes nothing | D3 |
| 12 | `general/model.md:306` | "There is no `DELETE /playthroughs/{id}`" — route vocabulary | D2 |
| 13 | `general/model.md:312` | known gap 1, "party position is undefined for multiplayer" — **resolved, not carried**: there is no party position by design | D12 |
| 14 | `general/architecture.md:23`-`:24` | "a `playthrough_members` table as the ownership root, and one character per member" — both halves | D2, D13 |
| 15 | `general/architecture.md:76`,`:78` | "state panel (HP, AC, inventory, **turn order**)" and "playthrough list" | D8, D2 |
| 16 | `general/glossary.md:16`,`:64` | **Initiative** and **Encounter** lose their caller | D8 (deferred) |
| 17 | `general/glossary.md:51`,`:58`-`:61` | the **Playthrough** term, and "Adventure run — … inside a playthrough"; also: nothing names the **seed player character**, the authored fixture this phase instantiates a PC from until phase 7's generator lands | D2, D10 |
| 18 | `general/app-vision.md:50`,`:54` | "turn order beside the narration"; "A playthrough list resumes …" | D8, D2 |
| 19 | `general/requirement-map.md:28`,`:32` | "per playthrough" in the cost and personality rows | D2 |

**Also, and separately from the contradiction list:**

- `docs/README.md:23` — the module index gains a `modules/playthrough.md` row; that file is written by this
  phase and is the module's own README-equivalent.
- `roadmap/Stage-01/README.md:315`-`:318` — the four open decisions this phase owns are **closed**: ownership
  (membership row, upheld), progress (two levels, D10), module placement (`playthrough`, D14), event cost
  (stored per event, D4). `:385`-`:386`, the two conditional rows, are resolved the same way.
- `roadmap/Stage-01/phases.md:71`, `:179` and `roadmap/Stage-01/README.md` (8 occurrences) use "playthrough"
  as the entity. **Roadmap documents are history** (`AGENTS.md`: "where a roadmap doc and the code disagree,
  the code wins"), so they are listed for completeness and I recommend **not** rewriting them — correcting
  history is how a register stops being trustworthy.
- `AGENTS.md` needs no change: it names no state entity.
