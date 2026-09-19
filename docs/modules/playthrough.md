# The playthrough module — the state a game accumulates

`playthrough` is the module that owns everything a game **accumulates while it
is played**: which campaign a player is running, who may act in it, which
adventures have been entered, every creature, item and fixture that exists in
the run, and the transcript of what happened. Authored campaigns and
adventures are not here — those are static files owned by the `content` module
(`docs/modules/content.md`) and read-only at runtime. The name is the
activity, not an entity: **no table is called `playthrough`**, and no row is "a
playthrough".

Today the module ships its five tables and their migrations, plus the surface
that starts a campaign run, gives it its character, renames it, reads it
back, enters its next adventure, appends to its transcript, reads that
transcript back, reports what it has cost and puts the run away (§8): a
service of eleven functions behind nine authenticated endpoints, plus one
command run by hand rather than an endpoint (§10). Moving between scenes,
completing an adventure and a game finishing remain future work; this
document describes the tables and the surface that exist, not the lifecycle
still to come.

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
- **Combat, turn order and initiative.** Deferred to the DM-turn phase; this
  phase builds no combat state. `events.turn_id` is the one forward-looking
  column, and it is a bare column with no referent (§7).

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
  why nothing outside this module can ask for it directly, is §10.
- **One function writes this table, and one endpoint reads the player's half
  of it** — `append_event` and the transcript read, §8. How ids end up
  ordering that read, and the one condition that makes doing so safe, is §9.

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
| `GET /api/v1/playthrough/campaign/{runId}/events` | The run's player-visible transcript, oldest first — `200` and the entries |
| `GET /api/v1/playthrough/campaign/{runId}/stream` | Tells the caller when the transcript above has grown — no cost route exists anywhere; §11 |

A run reads as `id, campaignId, contentVersion, title, status, createdAt` and
nothing else — the row, not its state. A character reads as `id, name,
currentHp, maxHp, armourClass` and nothing else (`CharacterRead`) — a
`GameObject` row (§6), narrowed to what a player needs to see of their own
sheet. An adventure run reads as `id, adventureId, status, startedAt` and
nothing else (`AdventureRunRead`) — the row itself, before anyone has moved
through it. An event reads as `id, type, turnId, payload, createdAt` and
nothing else (`EventRead`) — no `visibility`, because this endpoint only ever
answers `player`-visible rows, and no cost, because that is bookkeeping for
the run, not for the player reading it.

The service (`service.py`) exposes `start_campaign_run`, `list_campaign_runs`,
`get_campaign_run`, `create_character`, `rename_campaign_run`,
`archive_campaign_run`, `activate_campaign_run`, `enter_adventure`,
`append_event`, `list_events` and `run_cost`, called as `service.f(...)`.
Every one of them takes the acting user, and every one that takes a run id
calls the internal `_require_member` first — **except `append_event`**,
which is never called directly from a route and trusts the mechanic calling
it to have checked membership already (see below). A run belonging to
someone else and a run that does not exist answer identically — **not
found** — so no one can probe for the existence of another player's game.
`_require_writable`, also internal, raises `RunArchivedError` on an
`archived` run; `rename_campaign_run`, `create_character` and
`enter_adventure` call it right after `_require_member`. `run_cost` is the
one function on this list with no route calling it at all — §10.

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
this document exists to flag, is §9.

Errors this module raises: an unknown-or-foreign run and a campaign the
content does not know are **not found**; a run already started, a second
character on a run, a write against an archived run, an invalid status
transition, entering an adventure while one is already under way and
entering when none is left to enter are each a **conflict**
(`ALREADY_STARTED`, `CHARACTER_EXISTS`, `RUN_ARCHIVED`, `INVALID_RUN_STATUS`,
`ADVENTURE_ACTIVE`, `ADVENTURE_EXHAUSTED`); a payload that does not match its
type's shape is a **validation error** (`InvalidEventPayloadError`).

## 9. The transcript's order is the order of ids — and why that is only safe today

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

## 10. What a run has cost, and why there is no address for it

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

## 11. The live signal

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
