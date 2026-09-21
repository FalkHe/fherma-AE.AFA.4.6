# The playthrough module — the state a game accumulates

`playthrough` is the module that owns everything a game **accumulates while it
is played**: which campaign a player is running, who may act in it, which
adventures have been entered, every creature, item and fixture that exists in
the run, and the transcript of what happened. Authored campaigns and
adventures are not here — those are static files owned by the `content` module
(`docs/modules/content.md`) and read-only at runtime. The name is the
activity, not an entity: **no table is called `playthrough`**, and no row is "a
playthrough".

Today the module ships its five tables and their migrations, plus a service
of twenty-nine functions behind nine authenticated endpoints and two
commands run by hand rather than an endpoint. Together they carry a whole
game: starting a campaign run and giving it its character, renaming it and
reading it back, entering its next adventure and moving whoever is acting
through an exit (§8, §9); deriving and recording a roll and spending one
against a difficulty, and telling a reader of the transcript what the game
is waiting for as a result (§13–§15); a fixture's own authored checks and
the one-action rule every acting mechanic keeps, whatever it is a mechanic
for (§16, §17); an item changing hands three ways, and the placeholder
standing where using one will work once one can be written as consumable
(§18, §19); and a fight — striking a blow, wounding whoever it landed on,
and rolling to see who acts first — built from those same ordinary
mechanics rather than a state of its own (§20–§22). A tool layer letting
the Dungeon Master reach any of this belongs to a separate, later phase;
nothing in this document describes one, because none exists yet.

## 1. What the module owns, and what it does not

It owns five tables, declared in `backend/app/modules/playthrough/models.py`:

| Table | Model class | Migration | One row is |
|---|---|---|---|
| `campaign_runs` | `CampaignRun` | `0003_campaign_runs.py` | One campaign run: a player's game of one campaign, at one pinned content version |
| `campaign_run_members` | `CampaignRunMember` | `0003_campaign_runs.py` | One user's membership in a campaign run — who may act in it |
| `adventure_runs` | `AdventureRun` | `0004_adventure_runs.py` | One adventure entered within a campaign run |
| `objects` | `GameObject` | `0005_objects.py` | One creature, item or fixture instantiated within a campaign run |
| `events` | `Event` | `0006_events.py` | One entry of a campaign run's transcript |

It does **not** own:

- **Authored content.** `campaign_id`, `content_version`, `adventure_id`,
  `scene_id`, `template_id`, `source_adventure_id` and `source_scene_id` are
  all content ids: plain strings with **no foreign key**, because the thing
  they name is a JSON file, not a row.
- **Users.** `campaign_run_members.user_id` references `users.id`
  (`ON DELETE CASCADE`); the `auth` module owns that table.
- **SRD rules text.** That is the `srd` module's, reached through RAG.
- **An encounter, and whose turn it is.** Striking a blow, wounding whoever
  it landed on and rolling to see who acts first are ordinary mechanics this
  module owns like any other (§20–§22) — but nothing here opens or closes a
  fight, and no row anywhere says whose turn it is or in what order. Turn
  structure itself is deferred to the DM-turn phase; `events.turn_id` is the
  one forward-looking column, and it is a bare column with no referent (§7).

## 2. How the five tables relate

```
campaign_runs
├── campaign_run_members   (user_id → users.id)
├── adventure_runs
├── objects                (member_id → campaign_run_members.id)
│   └── objects            (owner_object_id → objects.id, carried)
│        ^ adventure_run_id → adventure_runs.id  (position)
└── events                 (actor_member_id → campaign_run_members.id)
```

Every table below the top hangs off `campaign_runs` directly, with
`ON DELETE CASCADE` on `campaign_run_id` — **a campaign run is the deletion
unit**, and nothing in the module is shared between runs. There are **no ORM
relationships** anywhere in `models.py`: every association is a foreign-key
column, loaded by an explicit query, never by attribute traversal.

## 3. `campaign_runs`

One player's game of one campaign, pinned to one content version for its whole
life, plus the model settings the Dungeon Master runs with.

| Column | Type | Null | Default | Purpose |
|---|---|---|---|---|
| `id` | ULID `CHAR(26)` | no | generated | Primary key |
| `campaign_id` | `String(64)` | no | — | The authored campaign, by content id — no FK |
| `content_version` | `String(16)` | no | — | The pinned version directory (`v1`, `v2`, …) |
| `title` | `String(120)` | yes | `NULL` | The player's own name for the run |
| `status` | `String(16)` | no | `setup` | `setup` / `ready` / `active` / `archived` / `finished` |
| `model` | `String(64)` | yes | `NULL` | OpenRouter model id this run uses |
| `temperature` | `NUMERIC(3,2)` | yes | `NULL` | Sampling temperature — an exact decimal, never a float, the same shape as `events.cost_usd` |
| `personality_prompt_id` | `String(128)` | yes | `NULL` | Which DM personality prompt to load |
| `system_prompt_override` | `Text` | yes | `NULL` | A full system-prompt replacement |
| `created_at` / `updated_at` | timestamptz | no | `now()` | `updated_at` also on update |

- **`status` is a lifecycle, not a free set of labels.** A run is created in
  `setup` — the row exists, but its character does not yet. Creating the
  character moves it to `ready`; the first narration written moves it to
  `active`. `archived` and `finished` follow as before. **Check `status`**:
  `status IN ('setup','ready','active','archived','finished')`.
- **No owner column.** Ownership lives in `campaign_run_members` (§4) and
  nowhere else, so that a run never has to be rewritten to gain a second
  member.
- The four model-settings columns are all optional: `NULL` means "whatever the
  application default is", not "no model".

## 4. `campaign_run_members`

Who may act in a campaign run. One row per `(campaign_run_id, user_id)` pair.

| Column | Type | Null | Default | Purpose |
|---|---|---|---|---|
| `id` | ULID `CHAR(26)` | no | generated | Primary key — the id `objects` and `events` point at |
| `campaign_run_id` | FK → `campaign_runs.id` | no | — | `ON DELETE CASCADE` |
| `user_id` | FK → `users.id` | no | — | `ON DELETE CASCADE`, indexed |
| `role` | `String(16)` | no | `owner` | `owner` is the only value today |
| `created_at` | timestamptz | no | `now()` | — |

- **Check `role`**: `role IN ('owner')`. **Unique**
  `(campaign_run_id, user_id)` — a user joins a run once.
- **The membership row, not the user, is what the rest of the module points
  at.** `objects.member_id` and `events.actor_member_id` both reference this
  id, so "who controls this creature" and "who took this action" are answered
  within the run.
- **A membership may control more than one creature**: the model lets a user
  control several characters in one campaign run; Stage-01 gameplay assumes
  one. `objects.member_id` is indexed but never unique (§6).

## 5. `adventure_runs`

One adventure entered within a campaign run — the progress record, one row per
`(campaign_run_id, adventure_id)` pair.

| Column | Type | Null | Default | Purpose |
|---|---|---|---|---|
| `id` | ULID `CHAR(26)` | no | generated | Primary key |
| `campaign_run_id` | FK → `campaign_runs.id` | no | — | `ON DELETE CASCADE`, not indexed |
| `adventure_id` | `String(64)` | no | — | The authored adventure, by content id — no FK |
| `status` | `String(16)` | no | `active` | `active` / `completed` |
| `started_at` | timestamptz | no | `now()` | When the adventure was entered |
| `completed_at` | timestamptz | yes | `NULL` | Set if and only if `status` is `completed` |
| `updated_at` | timestamptz | no | `now()` | Also on update |

- **Check `status`**: `status IN ('active','completed')`. **Check
  `completed_at`**: `(status = 'completed') = (completed_at IS NOT NULL)` —
  the two can never disagree.
- **Unique** `(campaign_run_id, adventure_id)`: an adventure gets at most one
  row for the life of the run — entering only ever picks an adventure with
  none yet, so no id is ever entered twice (§8). **At most one `active`
  adventure run per campaign run**, enforced by a partial unique index
  (`uq_adventure_runs_active … WHERE status = 'active'`), not a constraint —
  Postgres has no partial unique constraint, only a partial unique index.
- **No scene column and no party position.** Position belongs to the creature,
  not the party: the pair `(adventure_run_id, scene_id)` on its own `objects`
  row. No row claims a party position.

## 6. `objects`

A creature, an item or a fixture instantiated within a campaign run. The model
class is `GameObject` because `Object` shadows a builtin; the table is
`objects` and the prose noun is the kind — **creature**, **item**, **fixture**.

| Column | Type | Null | Default | Purpose |
|---|---|---|---|---|
| `id` | ULID `CHAR(26)` | no | generated | Primary key |
| `campaign_run_id` | FK → `campaign_runs.id` | no | — | `ON DELETE CASCADE`, indexed |
| `member_id` | FK → `campaign_run_members.id` | yes | `NULL` | `ON DELETE CASCADE`, indexed, **never unique** |
| `kind` | `String(16)` | no | — | `creature` / `item` / `fixture` |
| `template_id` | `String(64)` | yes | `NULL` | The authored `ObjectTemplate` it came from — no FK |
| `instance_key` | `String(160)` | no | — | Stable per-run identity (`goblin-2`) |
| `name` | `String(120)` | no | — | What the player is told it is called |
| `source_adventure_id` / `source_scene_id` | `String(64)` | yes | `NULL` | **Provenance** — where it was instantiated, written once |
| `adventure_run_id` | FK → `adventure_runs.id` | yes | `NULL` | **Position** — `ON DELETE SET NULL` |
| `scene_id` | `String(64)` | yes | `NULL` | **Position** — the scene within that adventure run |
| `owner_object_id` | FK → `objects.id` | yes | `NULL` | Self-referential: who carries it; `ON DELETE CASCADE`, indexed |
| `current_hp`, `max_hp`, `armour_class` | `Integer` | yes | `NULL` | Creature-only fighting stats |
| `is_alive` | `Boolean` | yes | `NULL` | Creature-only |
| `state` | `JSONB` | no | `'{}'` | Everything else the run needs to remember about it |
| `created_at` / `updated_at` | timestamptz | no | `now()` | — |

- **Unique** `(campaign_run_id, instance_key)`. Indexed on
  `(adventure_run_id, scene_id)` — "what is in this scene" is the one query
  the schema is shaped for.
- **`template_id` is optional.** It is absent exactly when the object was
  generated rather than instantiated from authored content — a generated
  character has no template. Nothing else changes for a generated object:
  the creature-only stats rule and the hit-point range rule below still
  hold.
- **Provenance and position are different pairs, and nothing ties them
  together.** `source_*` records where a thing came from and is written once;
  `(adventure_run_id, scene_id)` records where it is now and is rewritten on
  entry and on every move. A creature carried out of the scene it was
  authored into keeps its provenance unchanged.
- **Position belongs to the creature, not the party**: the pair
  `(adventure_run_id, scene_id)` on its own `objects` row. No row claims a
  party position. **Check `position`**:
  `(adventure_run_id IS NULL) = (scene_id IS NULL)` — both columns or neither,
  never half a position.
- **Check `carried`**: a row with an `owner_object_id` has no position of its
  own. A carried thing is located by its owner, so a sword in a pack moves
  when the pack does, with no row to update.
- **Check `stats_creature_only`**: `current_hp`, `max_hp`, `armour_class` and
  `is_alive` are present **if and only if** `kind` is `creature`. **Check
  `hp_range`**: `0 ≤ current_hp ≤ max_hp`. An item cannot acquire hit points
  and a creature cannot lose them.
- **`member_id` is what makes a creature a player character** — the player's
  own creature is instantiated from the **seed player character**, the
  authored fixture a campaign run instantiates the player's creature from
  until the generation agent lands. It is nullable (most rows are monsters and
  scenery) and never unique, because the model lets a user control several
  characters in one campaign run; Stage-01 gameplay assumes one.
- **Deleting an `adventure_runs` row that a positioned object still points at
  is rejected** by the `position` check rather than silently clearing the
  position — `ON DELETE SET NULL` would leave `scene_id` behind. Nothing in
  this codebase deletes an `adventure_runs` row, so this is a defended edge,
  not a live path.

## 7. `events`

One step of a campaign run's transcript — narration, player action, a
requested or resolved dice roll, a question put to the player, a tool call,
a scene or adventure milestone, a system message, or an error or warning.
Append-only: written once, never edited, never deleted.

| Column | Type | Null | Default | Purpose |
|---|---|---|---|---|
| `id` | ULID `CHAR(26)` | no | generated | Primary key — and, being a ULID, the chronological sort key |
| `campaign_run_id` | FK → `campaign_runs.id` | no | — | `ON DELETE CASCADE` |
| `actor_member_id` | FK → `campaign_run_members.id` | yes | `NULL` | `ON DELETE SET NULL` — the event outlives the member |
| `turn_id` | ULID `CHAR(26)` | yes | `NULL` | Groups events into one turn — **no foreign key** |
| `type` | `String(32)` | no | — | `narration` / `player_action` / `roll_requested` / `roll` / `question` / `tool_call` / `scene_entered` / `adventure_started` / `adventure_completed` / `system` / `error` / `warning` |
| `visibility` | `String(8)` | no | — | `player` / `dm` |
| `payload` | `JSONB` | no | **none** | The event body; its shape follows from `type` |
| `prompt_tokens`, `completion_tokens` | `Integer` | yes | `NULL` | Model usage for this event |
| `cost_usd` | `NUMERIC(12,6)` | yes | `NULL` | Exact decimal, never a float |
| `created_at` | timestamptz | no | `now()` | The only timestamp — there is no `updated_at` |

- **Checks** on `type` and `visibility`. Indexed on
  `(campaign_run_id, visibility, id)` — the player's transcript, in order —
  and on `(campaign_run_id, turn_id)`. **No unique constraint**: two identical
  narrations are two events.
- **`visibility` splits what the player may read from DM-only bookkeeping**,
  so hidden rolls and tool calls can be recorded in the same stream they
  happened in rather than in a second table.
- **`actor_member_id` is cleared, not cascaded.** Removing a member must not
  erase the history of what they did.
- **`turn_id` has no referent yet.** Turn structure is deferred to the DM-turn
  phase; this phase builds no combat state. The column is carried now so that
  events written before the turn concept exists can still be grouped by it,
  and it is a bare column precisely because there is no table to point at.
- **Cost is stored per event, not per run.** A run's spend is a sum over its
  events, which cannot drift from the events that caused it — there is no
  separate ledger row and nothing to keep in step. How that sum is read, and
  why nothing outside this module can ask for it directly, is §11.
- **One function writes this table, and one endpoint reads the player's half
  of it** — `append_event` and the transcript read, §8. How ids end up
  ordering that read, and the one condition that makes doing so safe, is
  §10.

## 8. Surface

Nine endpoints exist, all authenticated; `POST` and `PATCH` are also
CSRF-guarded:

| Method & path | Behaviour |
|---|---|
| `POST /api/v1/playthrough/campaign` | Starts a campaign run for `{"campaignId": …}` — `201` and the run |
| `GET /api/v1/playthrough/campaign` | The caller's runs, newest first, archived ones included |
| `GET /api/v1/playthrough/campaign/{runId}` | One of the caller's runs |
| `PATCH /api/v1/playthrough/campaign/{runId}` | Renames the run for `{"title": …}` — `200` and the run |
| `POST /api/v1/playthrough/campaign/{runId}/character` | Creates the run's one player character — `201` and the character |
| `POST /api/v1/playthrough/campaign/{runId}/adventure` | Enters the next adventure the campaign lists that this game has no record of — `201` and the adventure run |
| `POST /api/v1/playthrough/campaign/{runId}/archive` | Puts the run away, or deletes it if it was never started — `204`, no body |
| `GET /api/v1/playthrough/campaign/{runId}/events` | The run's player-visible transcript, oldest first, alongside what the game is waiting for — `200`, the entries and `awaiting`; §15 |
| `GET /api/v1/playthrough/campaign/{runId}/stream` | Tells the caller when the transcript above has grown — no cost route exists anywhere; §12 |

A run reads as `id, campaignId, contentVersion, title, status, createdAt` and
nothing else — the row, not its state. A character reads as `id, name,
currentHp, maxHp, armourClass` and nothing else (`CharacterRead`) — a
`GameObject` row (§6), narrowed to what a player needs to see of their own
sheet. An adventure run reads as `id, adventureId, status, startedAt` and
nothing else (`AdventureRunRead`) — the row itself, before anyone has moved
through it. An event reads as `id, type, turnId, payload, createdAt` and
nothing else (`EventRead`) — no `visibility`, because this endpoint only ever
answers `player`-visible rows, and no cost, because that is bookkeeping for
the run, not for the player reading it. The transcript read itself answers
more than a bare list of these: it wraps them alongside `awaiting`, one of
`none`, a roll's id or a question's id — §15 describes what that value
means and how it is worked out.

The service (`service.py`) exposes `start_campaign_run`, `list_campaign_runs`,
`get_campaign_run`, `create_character`, `rename_campaign_run`,
`archive_campaign_run`, `activate_campaign_run`, `enter_adventure`,
`use_exit`, `append_event`, `list_events` and `run_cost`, called as
`service.f(...)`. Every one of them takes the acting user, and every one
that takes a run id calls the internal `_require_member` first — **except
`append_event`**, which is never called directly from a route and trusts
the mechanic calling it to have checked membership already (see below). A
run belonging to someone else and a run that does not exist answer
identically — **not found** — so no one can probe for the existence of
another player's game. `_require_writable`, also internal, raises
`RunArchivedError` on an `archived` run; `rename_campaign_run`,
`create_character`, `enter_adventure` and `use_exit` call it right after
`_require_member`. `run_cost` is the one function on this list with no
route calling it at all — §11.

**Starting a run** does three things at once, because none of them makes
sense without the others: it pins the campaign's current content version onto
the run for its whole life, so a later change to the authored content cannot
alter a game already in progress; it makes the starter the run's owning
member (`campaign_run_members`, §4); and it instantiates every object the
campaign's adventures declare — every placement, every carried item — into
`objects` (§6), none of them positioned in any scene yet: positioning happens
only when that object's adventure is entered, a separate, explicit step
(below). **The player's own creature is not among them**: a run leaves
`start_campaign_run` in `setup`, its world populated but its character still
to come. It appends no `events` row (§7). Starting the same run twice is
refused by the uniqueness of
`(campaign_run_id, instance_key)` on `objects` (§6) rather than by an explicit
check.

**Creating the character** is the second, later step, and the only caller of
the generic object write for the player's own creature: `create_character`
reads a `SeedCharacter`-shaped sheet — the pinned campaign's own seed
character until a generation agent supplies one of its own, the signature
already accepting either — and builds one `objects` row with no
`template_id`, `member_id` set to the caller's membership, `instance_key`
`pc:<memberId>:1`, and `current_hp` equal to `max_hp`. It then builds one
carried `item` row per sheet inventory entry, through the same
template-driven `_build_object` `start_campaign_run` uses, each keyed
`pc:<memberId>:1/<templateId>:<n>` and none of them positioned. Both writes
flush before the run's `status` moves `setup → ready` and everything commits
once; no `events` row is appended. A second character on the same run is
refused (`CharacterExistsError`), checked by querying `objects` for an
existing `creature` at this `member_id` rather than by a constraint
(← 003-D13).

**Renaming** only sets `title`; the run's `status` is untouched.

**Archiving** is the run's shelf life, and there is no unarchive. `ready`,
`active` and `finished` all move to `archived`; an already-`archived` run is
a no-op. A run still `setup` was never given a character, so archiving it
instead **deletes it outright** — the run row, its membership and every
`objects` row instantiated for it — carried entirely by the schema's
`ON DELETE CASCADE` chain (§2) once the `campaign_runs` row goes. Every other
archive leaves the row, and everything under it, exactly as it was: the
event stream and the cost record it carries stay just as readable as before,
still reachable by `GET`, only no longer writable.

**Activating** a run — `activate_campaign_run`, `ready → active` — has no
route yet; it exists for the first-narration step a later phase adds to call.
Called on an already-`active` run it is a no-op; called on anything else it
raises `InvalidRunStatusError`.

**Entering an adventure** is `enter_adventure`, behind the new endpoint
above. It only runs against a `ready` or `active` run — anything else raises
the same `InvalidRunStatusError` activating a run raises on a bad transition
— then asks the run's pinned campaign for its adventure list and takes the
first id in it that this campaign run has no `adventure_runs` row for at
all: that is **the next adventure**, read from the campaign's own list every
time rather than from any pointer this module keeps, so "what is next" and
"is anything left" are both answered the same way. Nothing left to take
raises `AdventureExhaustedError` — the same refusal a completed adventure's
id would meet, since a row already existing is enough to skip it regardless
of what `status` that row holds; there is no re-entering an adventure once
it has one. Finding one, it inserts the new `adventure_runs` row and, in the
same transaction, positions two families of `objects` (§6): the adventure's
own cast — its creatures and fixtures, matched by `source_adventure_id`,
carried items excluded — moves to the scene each was authored into
(`scene_id = source_scene_id`); every member's character, wherever it was
made, moves to the adventure's `entry_scene`. Nothing else in the run is
touched, and a carried item stays with whoever carries it. It appends one
`adventure_started` event, visible to the player, carrying the new adventure
run's id, then commits once. **It does not move the campaign run's own
`status`**: a run becomes `active` at its first narration
(`activate_campaign_run`, above), not at its first adventure. **A second
entry while one is already `active` is refused** — `AdventureActiveError`,
raised when the insert collides with `uq_adventure_runs_active` (§5) rather
than by a check made ahead of the insert.

**Using an exit** is `use_exit`, and like activating a run it has no route
of its own — nobody outside this module calls it yet. It is the one
mechanic that moves an actor anywhere at all, whether that is a step to the
next scene or the end of the adventure they are in; §9 describes it in
full.

**Appending an event** is `append_event`, and it is the **only** function
anywhere in the tree that writes to `events` (§7) — nothing else in the
module, and nothing outside it, inserts a row there. It takes the run, the
entry's `type`, who may see it (`visibility`), the entry's payload, and
optionally the turn it belongs to, the member who caused it, and the model
usage it cost. It checks the payload — a dict or the type's own payload
model — against `EVENT_PAYLOADS[type]`, the twelve-entry registry in
`schemas.py` that fixes the shape each of the twelve kinds promises
(`narration`, `player_action`, `roll_requested`, `roll`, `question`,
`tool_call`, `scene_entered`, `adventure_started`, `adventure_completed`,
`system`, `error`, `warning`), and stores the validated result camelCase. An
unknown type, an unknown visibility, or a payload that does not match its
type's shape raises `InvalidEventPayloadError` and **writes nothing** — not
a partial row, not a row with a wrong-shaped payload. Model usage, when
given, copies its token counts across and turns its cost into
`Decimal(str(usage.cost_usd))`, never `Decimal(float)`, so the exact figure
survives. `append_event` `add`s and `flush`es, so the new row's id exists for
whatever caused it to be written, but it **never commits**: the mechanic
recording its own work — a roll, a scene entered, a tool called — commits
once, after it has also made whatever state change the event describes, so
the two land together or not at all. It makes **no membership check**,
because by the time anything calls it, something upstream already has.

**Reading the transcript** is `list_events`, behind
`GET …/{runId}/events`. It answers the run's `player`-visible events, oldest
first, in pages: `after`, an entry id, is exclusive — the answer starts
strictly after it — and `limit` defaults to 200 and never exceeds 500. The
DM-only entries `append_event` also wrote are never in this answer, though
they remain in `events` exactly as `archive_campaign_run` leaves the whole
table: present, and readable by anyone with a reason to read it directly,
just not through this endpoint. The ordering, and the one thing about it
this document exists to flag, is §10. The same endpoint also calls
`get_awaiting` and returns its answer alongside the entries, rather than
making a client ask twice for two things that describe the same open turn;
§15 covers what it derives and how.

Errors this module raises: an unknown-or-foreign run, a campaign the content
does not know, an actor or object id `use_exit`, `interact`, `take`, `drop`,
`give`, `use_item`, `attack` or `damage` cannot find, and a roll or hit id
no consumer below recognises are **not found**; a run already started, a
second character on a run, a write against an archived run, an invalid
status transition, entering an adventure while one is already under way,
entering when none is left to enter, asking `use_exit` for an exit it will
not take, spending a roll that is already spent, from a later turn or of
the wrong kind, resolving against a difficulty outside 5–30, `interact`
asked for an action its object never authored or for a check needing a
roll with none given and nothing carried that bypasses it, a second action
asked of a creature that has already spent this turn's, `take`, `drop`,
`give` or `attack` asked to reach an item or a target that is not reachable
from where the actor stands, `use_item` asked to use anything at all, and
`damage` asked to spend a hit that missed, belongs to another turn, names a
different target, or has already been paid out are each a **conflict**
(`ALREADY_STARTED`, `CHARACTER_EXISTS`, `RUN_ARCHIVED`,
`INVALID_RUN_STATUS`, `ADVENTURE_ACTIVE`, `ADVENTURE_EXHAUSTED`,
`EXIT_NOT_AVAILABLE`, `ROLL_NOT_USABLE`, `INVALID_DC`,
`ACTION_NOT_AVAILABLE`, `ROLL_REQUIRED`, `ALREADY_ACTED`,
`OBJECT_NOT_REACHABLE`, `ITEM_NOT_CONSUMABLE`, `HIT_NOT_USABLE`); a payload
that does not match its type's shape is a **validation error**
(`InvalidEventPayloadError`).

## 9. Using an exit: moving a scene, ending an adventure, finishing the game

**One mechanic moves anyone anywhere in this module: `use_exit`.** It takes
who is acting and which exit they take, and nothing else — no destination is
ever an argument, so nobody can be sent somewhere the content the campaign
actually declares does not lead. Scene change and the end of an adventure
are the same act by this account: both are just which kind of exit was
taken. It has no route of its own (§8) — the only thing meant to call it is
the Dungeon Master's own tool layer, a later phase's work, so this section
describes it by what it does rather than by how to reach it.

`use_exit` first loads the actor by id alone; an id the module does not
know at all answers **not found**, the same way an unknown run does
elsewhere in this document. Finding it, it checks membership on the
actor's own campaign run exactly as every other write in this module
does — a foreign actor answers identically to a missing one — then that the
run is writable and `ready` or `active`. It then reads the actor's current
scene from the content pinned to that run at the moment it started (§3),
through the content module, and looks for the requested exit among that
scene's own exits. **The exit's condition — the prose describing when it
may be used — is never read here.** It is written for the Dungeon Master to
weigh before ever reaching for this mechanic, not for the mechanic to
enforce; `use_exit` only ever checks that the exit exists on the actor's
scene, nothing about whether the story says it should be taken.

An exit found and of the ordinary kind **moves the actor**: its position
(§6) is rewritten to the scene the exit leads to, and nothing else about it
changes — which adventure the actor is in is untouched, since an exit only
ever changes where within it someone stands. A `scene_entered` event,
visible to the player, records the adventure run and the scene now entered.

An exit found and marked as **ending the adventure** does something
different: instead of moving anyone, it completes the adventure run the
actor is in — `status` becomes `completed`, `completed_at` is set to
now — and an `adventure_completed` event, visible to the player, records
which adventure run that was. When the adventure just completed is the
last one the pinned campaign's own list names, the campaign run itself
becomes `finished` in the same stroke. **Nobody is moved or cleared away
when an adventure ends.** Every object stays exactly where its own row
already placed it — deliberately, so that everything the transcript already
describes can still be read against a world that has not been swept away
underneath it.

Either outcome — a move or an ending — also appends one further event once
the state change itself has succeeded: a `tool_call` recording that the
mechanic ran and succeeded, visible only to the Dungeon Master, alongside
the `scene_entered` or `adventure_completed` entry the player does see.

**A refusal the player never sees, but the record keeps.** Asking for an
exit that is not among the actor's own scene's exits — or asking on behalf
of an actor with no scene to look one up on at all — is refused before
anything about the run, the actor or any other object changes: nothing
about the world is touched. The refusal is still written down, as its own
`tool_call` event, visible only to the Dungeon Master, naming the mechanic,
the actor it was asked for and the exit that was asked for, marked refused
rather than succeeded — written and kept even though the call itself then
fails, because a record of what was attempted is exactly what a refusal is
for. Only once that record is safely down does `use_exit` raise, so the
attempt is never lost to whatever happens next. The player's own reading of
the transcript (§8) shows nothing for a refusal, since it is
Dungeon-Master-only like the success record above it, so a player watching
their own game never sees a gap where a mistake happened — only ever the
moves and endings that actually took hold.

## 10. The transcript's order is the order of ids — and why that is only safe today

The read in §8 does exactly one thing to put the transcript in order: it
sorts `events` by `id`. Nothing else — no `created_at`, no sequence column,
no `ORDER BY … , id`. That is enough today because `id` is a ULID, which
sorts chronologically by construction, and because **one process** mints
every id this module ever writes: the whole backend runs as a single
process, so every id it hands out is drawn from that one process's own clock
and its own counter, and comparing two ids is the same as comparing when
they were minted.

That guarantee belongs to the process, not to the id format. A ULID's
ordering comes from its own generating process's clock, read at millisecond
resolution. Two ids minted by *different* processes in the same millisecond
carry no relationship to each other beyond that shared millisecond — each
process's clock and counter are its own. If this API ever ran as more than
one process, two events genuinely appended one after the other could be
minted by two different processes in the same millisecond, sort in the
wrong order, and a reader paging the transcript would see them swapped —
silently, since nothing about the read would signal that anything had gone
wrong.

The project accepts this today because the app runs as one process end to
end, so the failure mode above cannot occur. The fix is known and is not
being built now: a database-issued sequence — an integer the database itself
hands out as each row is inserted, ordered by the database's own commit
order rather than by a client-generated id — would remove the dependency on
a single minting process, at the cost of a schema change and a second sort
key everywhere the transcript is read. That cost is not worth paying before
the app has a reason to run as more than one process. **Anyone adding a
second process to this API must revisit this ordering before anything
else** — it is the one thing in this module that a second process would
silently break.

## 11. What a run has cost, and why there is no address for it

Every `events` row can carry what the model call behind it cost (`cost_usd`,
§7), and **a run's cost is nothing more than the sum of that column over its
events** — there is no separate ledger table, no running total kept on
`campaign_runs`, and so nothing that could ever drift out of step with the
events that actually happened. It can be read two ways: whole, as one figure
for the entire run, or broken down turn by turn, grouped by `events.turn_id`
with the entries that belong to no turn — recorded before the turn concept
existed, or never assigned one — gathered into one group of their own at the
end rather than left out. Either way the figure is **exact**: `cost_usd` is a
decimal column, summed as a decimal throughout, never rounded through a
float, so a run built from many small charges reports the number those
charges actually add up to, not a number close to it.

Nothing about this is reachable over the network. The only way to ask what a
run has cost is a command run by hand: `app playthrough cost <run-id> --user
<user-id>`, which prints the run's total and then one line per turn. It is
gated exactly like every other read in this module — the user must be a
member of the run, and asking about someone else's run answers the same
"not found" a foreign run gets anywhere else in the module, not a number.

**Cost has no address because it is a developer's number, not a player's.**
Nobody playing a game needs to see what their turn cost in model spend; the
figure exists to let whoever is running this service watch what it is
spending. The plan for it is a developer-only corner of the web client — a
drawer that does not exist yet — and until that drawer is built, a
command run by hand is the only way to look, on purpose: no endpoint answers
this figure, so there is nothing for a stray request, a curious player or a
future feature to stumble onto and expose by accident. A test in this
module's suite asserts that no route serves cost, so that absence stays true
as the module grows rather than quietly disappearing the day someone adds a
convenient endpoint.

## 12. The live signal

A player's client can hold open `GET
/api/v1/playthrough/campaign/{runId}/stream` and be told, without asking
again and again, when something new has happened in their game. What it is
told is deliberately thin: that there is something new, and which entry is
the newest one now — nothing about what that entry says. On seeing the
signal, the client re-reads the transcript the ordinary way, through the
`GET …/events` read already described in §8. That is the whole point of
keeping the signal empty: there is exactly one way to read what happened in a
game, and the stream only ever tells a client that it is time to use it
again, rather than becoming a second copy of the transcript that could one
day disagree with the first.

In plain terms, it behaves like any other server-sent event stream a browser
already knows how to consume. It checks, on a short interval, whether a new
entry has arrived; when one has, it sends the "something is new" message; when
nothing has changed, it sends a keepalive instead, so a connection sitting
quietly is not mistaken by anything in between for one that has died. It
closes itself either when the listener has gone away or once it has been open
for a bounded length of time, whichever comes first — and because this is an
ordinary server-sent event stream, the browser simply reconnects on its own
when that happens, so a player never notices the seam. Both the checking
interval and the maximum lifetime are settings with sensible defaults, not
values baked into the code.

There is no background worker behind this and nothing subscribes to the
database for changes: the stream simply polls, on its own schedule, for
whether anything new has landed since it last looked. At the size this game
runs at, one connection quietly asking "anything new?" a few times a minute
is enough, and it costs nothing to build beyond what already exists. Access
is checked once, **before** the stream is handed back to the client — so a
player who may not read this run is refused the same way they would be
refused anywhere else in this module, as an ordinary error, rather than being
handed a connection that opens and then goes silent for reasons they cannot
see.

## 13. A roll is derived, never handed a number

**The server rolls; nobody hands it a number.** Every roll is worked out
from exactly two things: what kind of roll it is, and who is rolling. An
attack uses the weapon's own to-hit; damage uses that same weapon's damage;
an ability check or a saving throw uses the modifier of whichever ability is
named; initiative always uses Dexterity, no matter what else is asked for.
One kind stands apart — a **custom** roll, whose expression is given
outright rather than derived from anything — and a custom roll can never
also carry a derived bonus: a roll is one or the other, never both. This is
not a rule kept by care. None of the functions below takes a parameter
named `formula`, `modifier`, `bonus`, `faces` or `total` — there is no
argument through which a number could be passed in at all, worth saying
plainly, because it is the reason the Dungeon Master cannot cheat a roll,
on purpose or by accident.

**A monster's attack belongs to the monster, not to an item it carries.** A
creature keeps its own attacks on its own stat block, and a creature may
have more than one; only a player's own weapon supplies an attack from an
item instead. Either way, the Dungeon Master names *which* attack, by name,
never by position — a stat block with more than one attack leaves no other
way to say which was meant — and the server still derives every number
that follows from it. The Dungeon Master chooses the intent; the server
still owns the arithmetic.

**Ability modifiers follow the SRD's own table**: a score of 10 or 11
carries no modifier at all, and every two points above or below moves the
modifier by one — the same rule the content module's own difficulty
numbers already assume (`docs/modules/content.md`).

**Four ways a roll happens.**

- *Asking the player to roll* records the request: what kind of roll it is,
  who it is for, and the formula the server derived for them — nothing
  resembling a result yet. The player's own click, later, is what answers
  it, and answering re-uses the very formula the request already stored
  rather than working it out a second time, so nobody is quietly promised
  one formula and given a roll made against another.
- *Rolling outright* does both steps in the same breath — deriving and
  rolling at once — and is how the Dungeon Master rolls on a creature's
  behalf, or makes a roll the player is not meant to see at all.
- *A passive check* is neither of those: it is settled without touching a
  single die, and is recorded for the Dungeon Master alone.
- *Asking a question* is its own kind of entry, and not a roll at all: the
  Dungeon Master puts something to the player in plain words, and the
  transcript records exactly that.

**What a roll records**: the individual dice as they actually fell, the
modifier that was added, and the total — nothing is ever re-rolled or
re-derived afterwards. A transcript can always be replayed from what it
already stored, never by working the numbers out again.

**A roll is recorded at the visibility its own request carried.** A roll
the Dungeon Master asked for in secret stays the Dungeon Master's; nothing
later widens or narrows who may see it. Whether that roll passed or failed
is deliberately not part of it — that judgement belongs to whichever
mechanic goes on to spend the roll, resolving it against a difficulty on an
entry of its own, never on the roll's own record. What spending a roll
means, and the rules that keep it from being spent more than once, are §14.

## 14. A roll is spent once

**A roll on its own says only how the dice fell.** Turning it into an
outcome — a pass or a fail — is a separate act: **resolving a check**, or
**resolving a saving throw**, against a difficulty. Either act reads a roll
already sitting on the transcript, never rolls dice of its own, and records
what came of it on an entry of its own: the total the roll carried, the
difficulty it was weighed against, and whether it succeeded, visible to the
Dungeon Master, and answers pass or fail back to whatever asked for the
roll to be spent. Worth stating plainly, because it is a deliberate shape:
**whether a roll passed is never written on the roll itself**, only on the
mechanic that spent it. One roll can therefore be looked at, or shown to a
player, without that alone implying anything it was part of has been
settled.

**The same roll cannot be spent twice.** Once a spend against a roll has
succeeded, a second attempt to resolve that same roll is refused, whichever
of the two mechanics asks. A roll also cannot be spent in a turn later than
the one it was rolled in, and cannot be spent for a kind of thing it was
not rolled for — a roll made for a saving throw is not available to a
check, and the reverse. A roll made from a bare expression rather than
derived from the actor — a **custom** roll, §13's one kind whose number a
caller supplied outright — is refused by both mechanics as a matter of
course: it is the one roll a caller supplied a number for, so it may never
be allowed to settle anything.

None of this is tracked in a column recording whether a roll has been used.
It is read from the transcript itself, every time: the roll's own entry is
there, and so is every entry that has already spent something, and the
rules above follow from comparing the two. There is nothing to keep in step
and nothing to migrate — only the transcript, read again.

**A refusal does not burn the roll.** Only a spend that succeeds counts
against a roll, so a mistaken attempt — the wrong turn, the wrong kind, a
roll already spent — leaves the player's roll exactly as good as it was
before the mistake. Every refusal is still recorded, as its own entry
visible to the Dungeon Master alone and marked refused, and that record
survives the refusal that produced it, exactly as a refused exit's does
(§9) — a player reading their own transcript sees no gap where a mistake
happened, because the attempt was never theirs to see in the first place.

**The difficulty a check or a saving throw is resolved against runs from 5
to 30** — the SRD's own table of difficulties, and the same range adventure
content is authored against (`docs/modules/content.md`). A difficulty
outside that range is refused and recorded exactly as an unusable roll
is — the roll itself is never spent.

## 15. What the game is waiting for

Reading a game's transcript now also answers a question no earlier read
of it did: is the game waiting on something right now, and if so, on what?
The answer is one of three shapes — nothing is awaited, a particular roll
the player has been asked to make, or an answer to a particular question
put to them — and it is worked out from the open turn's own entries each
time it is asked, never read from a value anything keeps in storage. A
requested roll with nothing yet spending it is a roll still awaited; a
question with no answer after it is a question still awaited; anything
else, and the game is waiting on nothing. There is no stored cursor
pointing at what is awaited, so nothing about this can ever fall out of
step with the transcript it is read from — every answer comes from asking
the transcript again, not from consulting a copy of it.

This travels with the transcript itself rather than behind a read of its
own: the same endpoint that answers a run's events (§8) now answers what
the game is waiting for in the same breath, so a client showing a player
their game is told, without a second question, whether it should now put a
roll or a question in front of them, or neither.

## 16. Interacting with a fixture

A fixture standing in a scene — a thorn screen barring a path, a door with a
lock that still holds — carries the ways it can be dealt with, written by
the adventure's own author: each one an authored check naming an action in
plain prose, the difficulty the author fixed for it, what becomes true once
it succeeds, and sometimes a list of items that get past it without any
roll at all (`FixtureTemplate.checks`, `docs/modules/content.md`).
**Interacting** is the one mechanic that acts on that list. It names the
actor attempting something, the fixture it is attempted against, and —
by the check's own wording, matched exactly rather than guessed at from a
synonym — *which* of the fixture's authored checks is being attempted, and
optionally a roll answering it. Like using an exit and every roll mechanic
before it (§9, §13), it has no route of its own yet: the only thing meant
to reach it is the Dungeon Master's own tool layer, later work.

An attempt passes one of two ways. Fed a roll, it passes when that roll —
spent through the very rule that already keeps a roll from being spent
twice (§14), so a roll interacting has spent is exactly as gone as one an
ability check or a saving throw spent — carries a total that meets or beats
the check's own difficulty; a roll of the wrong kind, already spent, from a
later turn, or a bare custom roll is refused here exactly as §14 already
refuses each of them. Fed no roll at all, it passes instead when the actor
is carrying something the check's own list of bypassing items names — a
key for the lock, a blade for the rope — consulted only because no roll was
offered, never as a shortcut around one that was; which item answered it is
written down alongside the pass. Anything else is refused before anything
is touched: an action the fixture's author never wrote for it, a check that
needs a roll when none was given and nothing the actor carries bypasses it
either, or a roll that was made for something else entirely.

**Interacting changes nothing in the world.** It reads the fixture's
authored checks and the actor's own carried things, and writes only what
was attempted and what came of it to the transcript — never a row anywhere
else. What a check's own success promises — a screen that no longer bars
the way, a door that gives — is prose the adventure's author wrote for the
Dungeon Master to narrate, not a change this mechanic makes on its own; a
fixture interacted with successfully looks, to every other row this module
keeps, exactly as it did before. That is a deliberate limit of what this
stage of the module does, worth saying plainly because it reads like an
oversight otherwise — the write that lets a passed check actually move
something in the world is later work, layered on top of what this mechanic
has already decided.

**Every attempt is recorded, a pass and a refusal alike.** A pass appends
one `tool_call` event naming the actor, the fixture, the action attempted,
the difficulty it was weighed against, the roll's own total when a roll
answered it or which carried item bypassed it when none did, and that it
succeeded. A refusal appends the same shape of entry marked refused
instead, visible only to the Dungeon Master — exactly as a refused exit is
(§9) and a roll's own refused spend is (§14) — committed on its own before
the refusal is raised as an error, so the attempt is never lost to whatever
happens next. A player reading their own transcript sees no gap where the
mistake happened, only ever the passes that actually took hold.

## 17. One action per creature per turn

**A creature gets one action in a turn.** Interacting with a fixture (§16),
taking an item, giving one, using an item (§18, §19) and attacking (§21)
each spend it — five actions in all, checked by the same rule before any of
them looks at what it was actually asked to do, so landing the last of them
cost this rule no rewrite.

**Dropping something does not spend the turn.** Neither does moving through
an exit (§9), rolling dice (§13), nor resolving a check or a saving throw
against a difficulty (§14) — none of those was ever a creature doing
something to someone or something else, which is what the rule above
actually guards. Dropping stands apart from the four actions above it only
because the SRD makes a point of it: dropping what you are carrying is
free, and this module keeps it exactly that free rather than folding it in
among the things that cost a turn — a creature can let go of everything it
holds and still act besides.

**A refused attempt does not spend the turn either.** Whatever a mechanic
refuses an attempt for — an action its target never authored, a roll it
needed and was not given, a roll it was given but could not use, or the
one-action rule itself — costs the creature nothing beyond the refusal
recorded against it (§16); a mistake is not the thing this rule spends a
turn on. A creature that tries and fails may simply try again, the same
turn, for as long as what it tries keeps failing rather than succeeding.

**A second action by the same creature within an open turn is refused
outright**, whichever of the five it is and whichever mechanic it was
asked of, before whatever was attempted is even looked at. **The count
behind that refusal is read from the transcript, not from anything
stored**: the creature's own actions that already succeeded within the
turn still open, asked again every time exactly the way §15 already
answers what a game is waiting for by reading the transcript rather than
consulting a value kept anywhere — there is no counter on the creature, on
the turn, or on the run, and so nothing about it can ever fall out of step
with what the transcript already shows. A turn that has not seen this
creature act yet carries no such history, so a fresh turn always lets it
act again.

## 18. Moving an item: picking it up, putting it down, handing it over

**Three mechanics move an item, and nothing else does.** Picking one up
puts it in the actor's own hands and takes it off wherever it lay. Putting
one down is the reverse: it leaves the item behind in the scene the actor
is standing in. Handing one over moves it straight from one creature's
hands to another's. Between the three of them, this is the whole of how an
item's owner ever changes: there is no mechanic that sets an item's owner
directly, and no number any caller passes ever decides where something
ends up — each of the three reads only who is acting, on what, and
sometimes who else is involved, exactly as using an exit reads only who is
acting and which exit (§9). Like every mechanic before them meant for the
Dungeon Master's own tool layer, none of the three has a route of its own
yet; this section describes what each one does rather than how to reach
it.

**Everything must be within reach, and reach means the same scene** — with
one widening. Picking an item up succeeds when the item lies, unclaimed,
in the actor's own scene, or when whatever currently holds it is a
**container** — a non-creature object — standing in that same scene: a
sack left on the floor can be looted this way, which is how the stolen
fleece comes out of the wool sack in Greenhollow. The widening reaches no
further than that: an item held by another *creature* cannot be picked up
by this mechanic at all — reach opens up for a container, never for
somebody's pockets. Handing an item over needs both creatures, the one
giving and the one receiving, standing in the same scene, and the item
must already be the giver's own to hand over. Putting an item down needs
only that the actor is carrying it. An actor standing in no scene at
all — nowhere on the map, in no adventure — can do none of the three.

**What a turn costs differs by which of the three it is.** Picking
something up and handing it over each spend the acting creature's one
action for the turn, the same action §17 already describes, refused a
second time in one turn regardless of which action-spending mechanic asks
for it. **Putting something down costs nothing at all** — the SRD makes a
point of this, and this module keeps it exactly that free rather than
folding it in among the things that spend a turn. A creature can therefore
pick something up and put something else down in the same turn, since only
one of those two draws on the turn's action, but it can never pick
something up twice in that same turn.

**Every attempt is recorded, a move and a refusal alike.** A move that
succeeds is written down as its own entry naming the mechanic, the actor
and the item — handing one over also names who received it — visible only
to the Dungeon Master, alongside whatever state actually changed. A
refusal is recorded the same way, marked refused rather than succeeded,
on its own before the mistake is ever raised as an error — the same
pattern every refusal already kept in this document (§9, §14, §16) — so a
player reading their own transcript never sees a gap where a mistake
happened, only the moves that actually took hold.

## 19. Using an item: the seam, not yet the mechanic

**A fourth mechanic exists for using an item, and today it refuses every
attempt.** It names the actor, the item, and optionally who or what the
item is used on, and it currently answers every single one of those
attempts the same way: refused, because no item this game's adventures
author can yet be written as something that gets used up or spent —
nothing about an item today says whether it can be used at all. The
mechanic is checked against the one action of §17 and §18 first, so a
creature that has already acted this turn is turned away for that reason
rather than for the item; but since only a successful act spends a turn,
a refusal here costs the creature nothing.

**This is a placeholder, on purpose.** It exists now so the shape of using
an item — an actor, an item, an optional target, one action spent, one
outcome recorded — is already settled before there is anything for it to
actually do. When a consumable item is eventually added to this game, it
arrives as a new kind of item and a branch placed in front of this
mechanic's blanket refusal, checked before that refusal fires rather than
instead of it; nothing else about the mechanic changes — not what it is
asked for, not the turn it spends, not how its outcome is written down.

**A refused use is recorded exactly like every other refusal in this
document** (§9, §14, §16, §18): its own entry, naming the attempt, visible
only to the Dungeon Master, written down before the mechanic raises its
refusal as an error, so nothing a player reads ever shows a gap where an
attempt to use something was quietly swallowed.

## 20. A fight is nothing but its acts

**There is no fight to open or close.** Striking a blow (§21), wounding
whoever it landed on (§22) and rolling to see who acts first, below, are
three ordinary mechanics, and nothing in this module remembers that any of
them happened beyond the ordinary transcript entries each one already
writes on its own: no table names an encounter, no column says two
creatures are fighting, no row holds a turn order, and no flag anywhere is
set when a fight starts and unset when it ends. **Rolling to see who acts
first does exactly what its name says and nothing more**: given the two
sides, whichever creature on a side is a member's own character is asked to
roll rather than rolled for outright, through the very request §13 already
describes, so a player's own click still decides their side's roll; a side
with nobody's own character on it is rolled by the server there and then,
at the visibility a player may see, the same way any other creature's roll
already is (§13). Either way the two resulting `roll` events, one
`initiative` roll per side, are the whole of what asking who goes first
leaves behind — no row anywhere is touched, and no `tool_call` is appended
either: nobody's turn is spent by finding out who goes first, so there is
nothing here for a refusal or a pass to be recorded against.

**Striking at someone and wounding them work in any scene, not only one the
Dungeon Master has decided is a battle.** An ambush sprung on someone still
exploring is simply an attack made during exploration, no different in this
module's eyes from one made after both sides have rolled to see who goes
first — attacking and wounding are ordinary acting mechanics, gated and
recorded exactly like every other one in this document, not a mode the game
has to be switched into first.

**This is deliberate, not an omission still to be filled in.** What
happened in a fight is already legible from the transcript alone — who
swung, at what, with what roll, whether it landed, how much it hurt, who is
still standing — because every mechanic in §21 and §22 writes exactly that
down as it happens, the same way every mechanic in this document already
does (§9, §14, §16, §18, §19). A second record of the same events, kept in
a column or a table of its own, could only ever agree with the transcript
when it is right and disagree with it the moment either one drifts, and
there is no way for the two to disagree that improves on simply reading the
one record that is always current. A test in this module's suite plays a
whole fight to its end and then asserts three exact sets against what the
schema actually holds afterwards — every table in the database, every
column on `objects` and on `events`, and every key ever written into an
object's `state` — so that an encounter table, a turn-order column or an
`in_combat` flag slipped in by some later change is caught by the
comparison itself rather than waved through by a check that only looks for
the obvious names.

## 21. Attacking

**An attack is the sixth action-spending mechanic** (§17): it names who is
swinging, at whom, with what — an item id, when a player's own weapon is
doing the swinging, and nothing at all when a monster's own stat block
supplies the attack instead (§13) — and the roll already made for it. Like
every mechanic before it meant for the Dungeon Master's own tool
layer (§9, §13, §16, §18), it has no route of its own; this section
describes what it does rather than how to reach it.

`attack` runs the same gate every acting mechanic already keeps —
membership, the run `ready` or `active`, the one-action check (§17) —
before anything about the attempt itself is looked at. Past that it loads
the target and, when one is named, the item, refusing before anything is
touched (`OBJECT_NOT_REACHABLE`, the same code §18's mechanics already
raise for the same shape of mistake) if the target stands in another scene
or the actor is not the one carrying the named item. It then spends the
named roll exactly as an ability check or a saving throw does (§14): the
roll must be an `attack` roll, made this turn, not already spent, or the
attempt is refused `ROLL_NOT_USABLE` before anything else happens.

**The die decides, and the target's armour decides nothing against a
natural 20.** An attack is always rolled on a single d20, so the one die it
recorded is there to read: if that die came up 20, the attack is a
**critical hit** regardless of the total it made or the armour the target
wears. Short of that, the roll's total is weighed against the target's own
`armour_class`: reaching it is a **hit**, falling short is a **miss**.
**Nothing about the target changes either way** — an attack only ever
settles whether the blow landed, and that verdict, hit, miss or crit, is
written on the attack's own `tool_call` entry, never on the roll it spent,
exactly as every other resolved roll in this module keeps pass or fail off
the roll itself (§14).

**A monster swings with what it is, not with what it holds.** A player's
weapon supplies an attack from an item the same way a monster's own stat
block supplies one instead (§13) — naming no item at all is how `attack`
is asked for a monster's own attack, since there is nothing for it to check
is carried. Which attack is meant is still named outright, never guessed at
from position, the same rule §13 already keeps for a stat block with more
than one attack to choose from.

**Every attempt is recorded, a hit, a miss, a crit and a refusal alike** —
the same pattern every mechanic in this document already keeps (§9, §14,
§16, §18, §19): a pass appends one `tool_call` naming the actor, the
target, the item when one was named, the roll spent, and the outcome it
settled; a refusal appends the same shape marked refused, visible only to
the Dungeon Master, committed on its own before the refusal is raised as an
error. A player reading their own transcript never sees the attempt itself,
only whatever narration the Dungeon Master goes on to write around it — an
attack, landed or not, leaves nothing else for the player's own read of the
game to show.

## 22. Wounding, and what is left when there is nothing

**Damage never names its own target — it reads one off the blow that
landed.** `damage` takes a roll and a **hit id**: the id of an `attack`
entry already on the transcript, and it is that entry, not anything the
caller separately names, that says who is hurt. A `hit_id` naming anything
else — an entry from another mechanic, an attack that missed, one from a
turn already closed, one already paid out by an earlier call to `damage`,
or an attack whose own recorded target disagrees with whichever target the
caller named — is refused outright, before a die is even rolled, under one
new code, `HIT_NOT_USABLE`, kept deliberately apart from the codes a roll's
own consumption already raises (§14): a hit that cannot be spent is a
different mistake from a roll that cannot be, even though both guard
exactly the same thing — nothing spent twice.

Found and usable, `damage` spends its own roll — a `damage` roll, subject
to the very same once-only rule every other roll answers to (§14) — and
applies it: hit points fall by the roll's total, and never below zero; a
wound worse than what remains simply empties the creature rather than
going negative. **What happens at zero depends on who was hit.** A monster
with nothing left is simply **no longer alive** — the same `is_alive`
column §6 already reserves for exactly this becomes false. A player's
character is not treated the same way: **it stays alive, and is marked
down** instead, a new key added to what its `state` already remembers
(§6) alongside its abilities, race, class, background and appearance — the
whole column reassigned at once, the same way creating the character wrote
it in the first place (§8), because nothing about this JSONB column is
ever edited in place. **That is deliberate, and it stops exactly there**:
the SRD's own rule has a character at zero hit points *dying* — unconscious,
rolling death saving throws against slipping away entirely — and none of
that exists yet. What becomes of a downed character is left for the phase
that narrates to decide; this module only ever marks it and stops.

Every attempt is recorded the same way every other mechanic in this
document already keeps it: a wound applied appends one `tool_call` naming
the target, the roll spent, the hit it was bound to, how much was rolled,
how much was actually applied once the clamp took hold, the hit points
left, and whether the target is still alive or now down; a refusal appends
the same shape marked refused, on its own, before the error is raised.
`damage` makes no one-action check of its own — the attack it is bound to
has already answered that when it was made (§17, §21) — so a wound is
never turned away for a reason that belongs to the blow that caused it,
not to the paperwork settling it.

**One attack per turn, like every other acting mechanic** (§17): a
creature that has already spent this turn's action is refused before an
attack is even weighed against anything, and a refused attempt — at
attacking, or at anything else this document guards the same way — costs
it nothing: the turn is only ever spent by an attempt that lands somewhere,
never by one that is turned away.
