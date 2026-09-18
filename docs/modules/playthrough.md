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
that starts a campaign run, gives it its character, renames it, reads it back
and puts it away (§8): a service of seven functions behind six authenticated
endpoints. Entering an adventure, positioning objects and appending events
remain future work; this document describes the tables and the surface that
exist, not the lifecycle still to come.

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
- **Unique** `(campaign_run_id, adventure_id)`: entering the same adventure
  twice reuses its row. **At most one `active` adventure run per campaign
  run**, enforced by a partial unique index
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
  events, which cannot drift from the events that caused it.

## 8. Surface

Six endpoints exist, all authenticated; `POST` and `PATCH` are also
CSRF-guarded:

| Method & path | Behaviour |
|---|---|
| `POST /api/v1/playthrough/campaign` | Starts a campaign run for `{"campaignId": …}` — `201` and the run |
| `GET /api/v1/playthrough/campaign` | The caller's runs, newest first, archived ones included |
| `GET /api/v1/playthrough/campaign/{runId}` | One of the caller's runs |
| `PATCH /api/v1/playthrough/campaign/{runId}` | Renames the run for `{"title": …}` — `200` and the run |
| `POST /api/v1/playthrough/campaign/{runId}/character` | Creates the run's one player character — `201` and the character |
| `POST /api/v1/playthrough/campaign/{runId}/archive` | Puts the run away, or deletes it if it was never started — `204`, no body |

A run reads as `id, campaignId, contentVersion, title, status, createdAt` and
nothing else — the row, not its state. A character reads as `id, name,
currentHp, maxHp, armourClass` and nothing else (`CharacterRead`) — a
`GameObject` row (§6), narrowed to what a player needs to see of their own
sheet.

The service (`service.py`) exposes `start_campaign_run`, `list_campaign_runs`,
`get_campaign_run`, `create_character`, `rename_campaign_run`,
`archive_campaign_run` and `activate_campaign_run`, called as
`service.f(...)`. Every one of them takes the acting user, and every one that
takes a run id calls the internal `_require_member` first. A run belonging to
someone else and a run that does not exist answer identically — **not
found** — so no one can probe for the existence of another player's game.
`_require_writable`, also internal, raises `RunArchivedError` on an
`archived` run; `rename_campaign_run` and `create_character` call it right
after `_require_member`.

**Starting a run** does three things at once, because none of them makes
sense without the others: it pins the campaign's current content version onto
the run for its whole life, so a later change to the authored content cannot
alter a game already in progress; it makes the starter the run's owning
member (`campaign_run_members`, §4); and it instantiates every object the
campaign's adventures declare — every placement, every carried item — into
`objects` (§6), none of them positioned in any scene yet, because entering an
adventure is a separate, explicit step still to come. **The player's own
creature is not among them**: a run leaves `start_campaign_run` in `setup`,
its world populated but its character still to come. It appends no `events`
row (§7). Starting the same run twice is refused by the uniqueness of
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

Errors this module raises: an unknown-or-foreign run and a campaign the
content does not know are **not found**; a run already started, a second
character on a run, a write against an archived run and an invalid status
transition are each a **conflict** (`ALREADY_STARTED`, `CHARACTER_EXISTS`,
`RUN_ARCHIVED`, `INVALID_RUN_STATUS`).
