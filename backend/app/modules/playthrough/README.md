# playthrough

Owns a player's playthrough of a campaign and who may act in it.

## Owns

- The `campaign_runs` table (`models.py`): one playthrough per row —
  `campaign_id`, `content_version`, an optional `title`, a `status` tracking
  the run's lifecycle: `setup` (the row exists, its character does not yet),
  `ready` (the character is created), `active` (the first narration is
  written), then `archived` / `finished` as before (`server_default
  "setup"`), the model settings it runs with (`model`, `temperature`,
  `personality_prompt_id`, `system_prompt_override`, all optional) and
  `created_at` / `updated_at`. No owner column — ownership lives in
  `campaign_run_members`.
- The `campaign_run_members` table (`models.py`): who may act in a run —
  `campaign_run_id` and `user_id` (each `ON DELETE CASCADE`), a `role`
  limited to `owner` (`server_default "owner"`) and `created_at`. One row
  per `(campaign_run_id, user_id)` pair.
- The `campaign_runs` / `campaign_run_members` migration
  (`alembic/versions/0003_campaign_runs.py`).
- The `adventure_runs` table (`models.py`): one row per adventure entered
  within a campaign run — `campaign_run_id` (`ON DELETE CASCADE`, no index)
  and `adventure_id`, a `status` limited to `active` / `completed`
  (`server_default "active"`), `started_at`, `completed_at` (set if and only
  if `status` is `completed`) and `updated_at`. One row per
  `(campaign_run_id, adventure_id)` pair, and at most one `active` row per
  `campaign_run_id` (a partial unique index, not a constraint). No scene
  column and no ORM relationship.
- The `adventure_runs` migration (`alembic/versions/0004_adventure_runs.py`).
- The `objects` table (`models.py`, class `GameObject` -- `Object` shadows a
  builtin): a creature, item or fixture instantiated within a campaign run.
  `campaign_run_id` (`ON DELETE CASCADE`, indexed) and an optional
  `member_id` (`ON DELETE CASCADE`, indexed, never unique -- a member may
  hold any number of things); a `kind` limited to `creature` / `item` /
  `fixture`; an optional `template_id`, absent exactly when the object was
  generated rather than instantiated from authored content; `instance_key`
  and `name`; provenance
  (`source_adventure_id`, `source_scene_id`, no FK, written once) kept
  separate from position (`adventure_run_id` `ON DELETE SET NULL`,
  `scene_id`, written on entry and every move) -- both columns of a pair or
  neither; an optional self-referential `owner_object_id`
  (`ON DELETE CASCADE`, indexed) for a carried thing, which then has no
  position of its own; the four fighting stats `current_hp`, `max_hp`,
  `armour_class`, `is_alive`, present if and only if `kind` is `creature`,
  with `current_hp` always between `0` and `max_hp`; a `state` JSONB column
  (`server_default '{}'`); `created_at` / `updated_at`. One row per
  `(campaign_run_id, instance_key)` pair. No ORM relationship. Deleting an
  `adventure_runs` row that a positioned object still points at is rejected
  by the position check, not silently cleared -- nothing in this codebase
  deletes an `adventure_runs` row, so this is a defended edge, not a live
  path.

- The `events` table (`models.py`): one row per step of a campaign run's
  transcript -- narration, player action, a requested or resolved roll, a
  question put to the player, a tool call, a scene or adventure milestone, a
  system message, an error or warning, or one of four player-visible
  mechanic outcomes added in sprint 010/04 (an item moved, hit points
  changed, a way opened, a rule looked up) -- `campaign_run_id`
  (`ON DELETE CASCADE`) and an optional `actor_member_id`
  (`ON DELETE SET NULL` -- the event outlives the member); an optional
  `turn_id` with no foreign key, since no turn concept exists yet; a `type`
  limited to `narration` / `player_action` / `roll_requested` / `roll` /
  `question` / `tool_call` / `scene_entered` / `adventure_started` /
  `adventure_completed` / `system` / `error` / `warning` / `item_moved` /
  `hp_changed` / `way_opened` / `rule_looked_up` and a `visibility`
  limited to `player` / `dm`; a non-nullable `payload`
  JSONB column with no default; optional `prompt_tokens`,
  `completion_tokens` and `cost_usd` (an exact `NUMERIC(12,6)`, never a
  float); `created_at` only -- an event is never edited after it is
  written; an optional `embedding` (`VECTOR(1536)`) and `embedding_model`,
  populated only for `narration` rows. Indexed by `(campaign_run_id,
  visibility, id)`, by `(campaign_run_id, turn_id)` and by a partial HNSW
  cosine index (`ix_events_embedding_narration`) restricted to `type =
  'narration' AND embedding IS NOT NULL`; no unique constraint and no ORM
  relationship.
- The `events` embedding columns and index migration
  (`alembic/versions/0008_event_embeddings.py`).
- The four-more-event-types migration, widening `ck_events_type` to sixteen
  values (`alembic/versions/0010_more_event_types.py`, sprint 010/04),
  self-reversing and additive-only like `0007`'s own `events.type` step,
  which it mirrors.
- The dice engine (`dice.py`): `roll(expression)` parses `NdM+-K` and rolls
  it behind an `_rng()` seam (swappable in tests for a scripted sequence of
  faces), capped at 20 dice of at most 100 faces, raising
  `InvalidDiceExpressionError` (`VALIDATION_ERROR`) naming the offending
  expression on anything else. `derive_formula(kind, actor, context, *,
  campaign_id, version, item=None)` maps a `RollKind` and an actor to the
  formula that kind implies: an item's or a stat block's own attack
  (chosen by name through `context["attack"]`, matched case-insensitively
  — sprint 010/09, ← finding: a self-rolling DM tool call may not echo a
  content-authored attack name's exact casing — never by position), an
  ability's own modifier (SRD floor division) for `ability_check` /
  `saving_throw`, Dexterity for `initiative`, or, for `custom` alone,
  `context["expression"]` verbatim. A missing `context["ability"]` (or an
  unrecognised one) or a missing `context["expression"]` raises `ValueError`
  naming what is missing (sprint 010/09, ← finding) rather than a bare
  `KeyError` the calling tool cannot recover from. For `attack`/`damage`,
  an `item` row (sprint 009-02, WI2, AC5 — a sheet-born weapon row with no
  content template) reads its attacks from its own `state["attacks"]`;
  otherwise
  `context["item_id"]`'s content template, when given, or the actor's own
  stat block, exactly as before. Neither function has a `formula`,
  `modifier`, `bonus`, `faces` or `total` parameter — there is no argument
  through which a caller could pass one in.

## Surface

Twelve endpoints, in two path families under `/api/v1/playthrough`, all
requiring an authenticated caller (`POST` and `PATCH` are also
CSRF-guarded). Cost and rolling both have no endpoint at all — see the CLI
commands and the notes below the service list.

- `GET /api/v1/playthrough/runs` — the caller's runs read as a picker list
  (WI1, AC1/AC2): newest first, archived included, each carrying its
  pinned campaign's title and summary, adventures completed versus the
  campaign's total, and how many players are seated —
  `CampaignRunSummaryRead`. A run whose pinned campaign or version no
  longer loads still lists, with `unavailable: true` and no campaign copy;
  nothing raises. A sibling literal to `/campaign` (not
  `/campaign/{runId}`, which the path parameter would shadow).
- `GET /api/v1/playthrough/runs/{runId}/overview` — one run read as a full
  overview screen (WI2, AC3): the run itself, every member with username,
  role, a `ready` flag and the character card (sprint 009-07) when one
  exists, and the campaign's adventures in the campaign's own order with a
  clipped intro and a `done`/`active`/`unplayed` status —
  `CampaignRunOverviewRead`. A
  run whose pinned campaign or version no longer loads still answers `200`
  with `unavailable: true`, no campaign copy and an empty adventure list
  (AC2's twin); `members` is unaffected. A non-member and an unknown id
  are refused alike, exactly like every other read in this module.
- `GET /api/v1/playthrough/runs/{runId}/table` — one read for the play
  screen (WI2, sprint 010/05): the run, its pinned campaign's title, the
  current adventure and scene, and every seated hero's full sheet —
  `TableRead`, serving the screen's header, its party rail and the full
  sheet alike in one call. The current adventure and scene are the
  **caller's own hero**'s, never whichever `adventure_runs` row happens to
  read `status == 'active'` — `use_exit` completes a row without ever
  clearing anyone's position, so an active-row anchor would blank the
  header at exactly the moment an adventure ends. Both are `null` when the
  caller has no hero yet, the hero has entered no adventure, or the pinned
  content no longer loads; `campaignTitle` is `null` under that last
  condition alone. A non-member and an unknown id are refused alike.
- `POST /api/v1/playthrough/campaign` with `{"campaignId": …}` — starts a
  campaign run, answering `201` and the run.
- `GET /api/v1/playthrough/campaign` — the caller's runs, newest first,
  archived ones included.
- `GET /api/v1/playthrough/campaign/{runId}` — one of the caller's runs.
- `PATCH /api/v1/playthrough/campaign/{runId}` with `{"title": …}` —
  renames the run, answering `200` and the run.
- `POST /api/v1/playthrough/campaign/{runId}/character` — with no body,
  creates the run's one player character from its pinned campaign's seed
  sheet; with a `CharacterCreateRequest` body, builds it through
  `character_service.build_sheet` first (`VALIDATION_ERROR` on an illegal
  spread or pick) — either way moves the run to `ready`, answering `201`
  and the character.
- `POST /api/v1/playthrough/campaign/{runId}/adventure` — enters the next
  adventure the campaign's own list names that this run has no record of
  yet, positions that adventure's cast and every member's character, and
  appends an `adventure_started` event, answering `201` and the adventure
  run.
- `POST /api/v1/playthrough/campaign/{runId}/archive` — puts the run away
  (or, for a run still `setup`, deletes it outright — see §Owns), answering
  `204` with no body.
- `GET /api/v1/playthrough/campaign/{runId}/events` with optional `after`
  (an entry id, exclusive) and `limit` (`Query`, default 200, max 500) —
  the run's `player`-visible transcript, ordered by `id`, oldest first;
  `dm`-visible entries are never in the answer though they stay in the
  table. The response also carries `awaiting` — `service.get_awaiting`'s
  answer for the same run — alongside the entries, so a client reading the
  transcript is told in the same call what the game is waiting for.
- `GET /api/v1/playthrough/campaign/{runId}/stream` — `text/event-stream`
  (`cache-control: no-cache`, `x-accel-buffering: no`); membership is
  checked before the `StreamingResponse` is built, so a refusal is an
  ordinary error envelope, never a stream that opens and dies. Per poll:
  `data: {"type":"updated","id":"<ulid>"}\n\n` when the latest event id has
  changed since the last tick, else `: keepalive\n\n`. Carries no payload —
  the client re-reads `GET …/events` on receiving it (← D10).

A run reads as `id, campaignId, contentVersion, title, status, createdAt` and
nothing else. A character reads as `id, name, currentHp, maxHp,
armourClass, race, characterClass, level, abilities, appearance, backstory,
items` and nothing else — `CharacterRead`, the one hero shape shared by
every read that already returns one (sprint 009-07 adds the four card
facts; WI1 sprint 010/05 widens it further, no `isAlive`/`down` — ← D7).
`abilities` is `{strength|dexterity|constitution|intelligence|wisdom|
charisma: {score, modifier}}` — `Ability`'s `modifier` is
`dice.ability_modifier(score)`, computed once server-side. `backstory` is
`CharacterState.background` under its wire name; `appearance` and
`backstory` answer `""`, never missing, for an unset value. `items` is
`Item[]` (`id, name`), one entry per unit of carried quantity — identical
items arrive as separate rows and the client groups them. `race`/
`characterClass`/`level`/`appearance`/`abilities`/`backstory` are read off
the object's `state` column through `CharacterState`; `service.
character_read(obj, *, items=())` is the one place that builds it, shared
by the overview, the table read and the `POST …/character` route —
`items` are carried rows the caller already fetched, never queried inside
`character_read` itself. An adventure run reads as
`id, adventureId, status, startedAt` and nothing else — `AdventureRunRead`.
An event reads as `id, type, turnId, payload, createdAt` and nothing else —
`EventRead`; no `visibility`, no cost, no run id. The events route itself
answers `{events, awaiting}` (`EventsRead`), not a bare array — `awaiting`
is one of `"none"`, `"roll:<id>"` or `"answer:<id>"`.

`payload: dict[str, Any]` passes through unmapped — a new `type` (like the
four sprint 010/04 added: `item_moved`, `hp_changed`, `way_opened`,
`rule_looked_up`) needs a migration, a payload model and a registry entry,
and **no route, `EventRead`, `EventsRead` or generated client change** to
reach a caller; older transcripts simply hold no rows of a kind that did
not exist yet when they were written.

A run summary (`GET /runs`, `CampaignRunSummaryRead`) reads as `id,
campaignId, status, createdAt, campaignTitle, campaignSummary,
adventuresCompleted, adventuresTotal, playerCount, unavailable` and nothing
else — `campaignTitle`/`campaignSummary`/`adventuresTotal` are `null` and
`unavailable` is `true` exactly when the pinned content no longer loads;
`adventuresCompleted` and `playerCount` are always counted, from this
run's own rows rather than from content.

A run overview (`GET /runs/{runId}/overview`, `CampaignRunOverviewRead`)
reads as `id, campaignId, contentVersion, title, status, createdAt,
campaignTitle, campaignSummary, unavailable, members, adventures` and
nothing else. A member (`CampaignRunMemberRead`) reads as `userId,
username, role, ready, character` — `ready` is `character is not null`;
`character` is the member's own `CharacterRead` or `null`. A non-player
creature never flips `ready`, since only a member's own character carries
`objects.memberId`. An adventure
(`CampaignRunAdventureRead`) reads as `id, title, introExcerpt, status` —
`id` is the campaign's adventure id, not the `adventure_runs` row id, and
`introExcerpt` is the intro clipped to 200 characters at a word boundary
with a trailing `…` when it was cut. `campaignTitle`/`campaignSummary` are
`null`, `unavailable` is `true` and `adventures` is empty exactly when the
pinned content no longer loads; `members` reads the same either way, since
it never touches content.

A table read (`GET /runs/{runId}/table`, `TableRead`, WI2 sprint 010/05)
reads as `runId, runTitle, runStatus, campaignTitle, adventure, scene,
heroes` and nothing else. `adventure` (`TableAdventure`) reads as `id`
(the campaign's own adventure id), `runId` (the `adventure_runs` row id),
`title`, `status` (`"active"`/`"completed"`, `adventure_runs.status`
verbatim); `scene` (`TableScene`) reads as `id, name`. Both are the
**caller's own hero**'s current position (its `objects.adventure_run_id`/
`scene_id`), not whichever `adventure_runs` row reads `status == 'active'`
— `use_exit` completes a row without clearing anyone's position, so an
active-row anchor would blank the header at exactly the moment an
adventure ends. `heroes` is every member's `CharacterRead`, ordered by
member id — a seat with no character yet contributes no row here, unlike
`CampaignRunOverviewRead.members`, which always carries one row per seat.

Service functions (`service.py`), called as `service.f(...)`:

- `list_run_summaries` — `list_campaign_runs`'s own rows and order,
  enriched with one grouped count of completed `adventure_runs` rows and
  one of `campaign_run_members` rows, both keyed by `campaign_run_id`, and
  each run's pinned campaign reloaded through `_load_pinned` — cached per
  `(campaign_id, content_version)`, so two runs of one campaign load its
  content once. Reads only: no commit, no status change, no event.
- `_load_pinned` — `content_service.load_campaign` for one run's pin,
  catching `ContentError` alone (logging `playthrough_content_unavailable`)
  and returning `None`; anything else travels.
- `start_campaign_run` — pins the run's `content_version` for its whole
  life, makes the starter the run's owning member, and instantiates every
  object the campaign's adventures declare, all unpositioned — entering an
  adventure is a separate, later step. The player's own creature is not
  among them; it does not exist until `create_character` runs. Appends no
  event. Starting the same run twice is refused by the uniqueness of
  `objects.instance_key` rather than by an explicit check.
- `list_campaign_runs` — the caller's runs, newest first.
- `get_campaign_run` — one run by id.
- `get_run_overview` — one run's aggregate overview (WI2, AC3): members
  from one query joining `campaign_run_members` to `users` and
  outer-joining the whole `objects` entity on `member_id == member.id AND
  kind == 'creature'` (sprint 009-07: the full object, not just its name,
  so `character_read` can build the card), adventures from
  `_load_pinned(run)` paired with this run's own `adventure_runs` rows, in
  the campaign's own order. `None` from `_load_pinned` means `unavailable`,
  no campaign copy and no adventures — `members` is unaffected. Reads
  only: no commit, no status change, no event.
- `get_table` (WI2, sprint 010/05) — one aggregate read for the play
  screen: members and their characters from the same join
  `get_run_overview` uses, but only a seat with a character contributes a
  `heroes` row; items the same grouped-query way. The current adventure
  and scene are read off the **caller's own** member's character
  (`objects.adventure_run_id`/`scene_id`), paired with that id's own
  `adventure_runs` row and the pinned content's own adventure/scene titles
  — never the `adventure_runs` row that happens to read `status ==
  'active'`, since `use_exit` completes a row without ever clearing
  anyone's position. Both `None` when the caller has no hero, the hero has
  entered no adventure, or `_load_pinned(run)` answers `None`;
  `campaignTitle` is `None` under that last condition alone. Reads only:
  no commit, no status change, no event.
- `character_read` (sprint 009-07) — the one place a character `GameObject`
  becomes a `CharacterRead`, reading `race`/`characterClass`/`level`/
  `appearance` off `CharacterState.model_validate(obj.state)`; shared by
  `get_run_overview`, `get_table` and the `POST …/character` route.
- `_excerpt` — clips text to 200 characters at the last word boundary
  before the cut, `rstrip()`ped and closed with `…`; unchanged when it
  already fits.
- `create_character` — builds the run's one player character (`GameObject`
  with no `template_id`, owned by the caller's membership) from a
  `SeedCharacter`-shaped sheet, defaulting to the pinned campaign's own seed
  character, then one carried `item` row per sheet inventory entry through
  the same template-driven `_build_object` sprint 03 built, then moves the
  run `setup → ready`. Refuses a second character on the run
  (`CharacterExistsError`) and refuses an archived run (`RunArchivedError`).
  Appends no event; one commit. A `CharacterSheet` (sprint 009-02, WI2)
  writes its full state instead (`level`, `alignment`, `speed`,
  `proficiency_bonus`, `saving_throws`, `skills`, `equipment`) and one
  carried `item` row per unit of quantity of each `SheetItem`, with no
  content template of its own — same single commit boundary.
- `get_member_character` — the caller's own character on a run: gated by
  membership (`_require_member`), then the one `objects` row with
  `kind == 'creature' AND member_id == member.id`. No character yet raises
  `CharacterNotFoundError`. Reads only: no commit, no event, no status
  change.
- `rename_campaign_run` — sets the run's title. Refuses an archived run
  (`RunArchivedError`).
- `archive_campaign_run` — `ready` / `active` / `finished` move to
  `archived`; already `archived` is a no-op. A `setup` run — never given a
  character — is deleted outright instead: the run row, its membership and
  every object instantiated for it, all removed through the schema's
  `ON DELETE CASCADE` chain. There is no unarchive.
- `activate_campaign_run` — `ready → active`, already `active` a no-op,
  any other status `InvalidRunStatusError`. No route calls it: it exists for
  a later phase's first-narration step to call (← D3).
- `enter_adventure` — requires the run `ready` or `active`
  (`InvalidRunStatusError` otherwise); reads the next id off the pinned
  campaign's own adventure list — the first one this run has no
  `adventure_runs` row for — refusing with `AdventureExhaustedError` when
  none is left (a completed adventure's id is never entered again either).
  Inserts the new `active` row, then in the same transaction positions the
  adventure's cast (`source_adventure_id` match, carried items excluded) at
  each one's authored scene and every member's character at the adventure's
  `entry_scene`; nothing else is touched. Appends a player-visible
  `adventure_started` event, then (sprint 010/04, I2) a player-visible
  `scene_entered {adventureRunId, sceneId, sceneTitle}` for that same entry
  scene — the opening move otherwise left no such row at all — and commits
  once, both writes together. Leaves the campaign run's own `status`
  untouched — that changes at the first narration, not here. A second entry
  while one is `active` collides with `uq_adventure_runs_active` and is
  re-raised as `AdventureActiveError`.
- `use_exit` — the one mechanic that moves an actor anywhere, taking only
  who is acting and which exit they take; no destination is ever an
  argument. Loads the actor by id alone (`GameObjectNotFoundError` if
  unknown), then requires the run `ready` or `active` like every other
  write. Resolves the actor's current scene through
  `content.service.load_scene` at the run's pinned `content_version` and
  matches `exit_id` among that scene's exits — `Exit.condition` is never
  read; it is prose for the caller to weigh before reaching for this
  function, not a check this function makes. Not on that scene, or the
  actor has no scene at all, refuses before any write: it appends a
  DM-visible `tool_call` event naming the mechanic, the actor and the exit,
  `result: "refused"`, commits that one row on its own — `append_event`
  only flushes — and then raises `ExitNotAvailableError`. Found and
  `kind="scene"`: rewrites the actor's `scene_id` to `exit.to`, appends a
  player-visible `scene_entered {adventureRunId, sceneId, sceneTitle}` —
  `sceneTitle` (sprint 010/04, I2) is the destination's own pinned title,
  read through `content.service.load_scene`, never a tool argument. Found
  and
  `kind="adventure_end"`: sets the actor's `adventure_runs` row
  `completed`/`completed_at`, appends a player-visible
  `adventure_completed {adventureRunId}`, and — when the pinned campaign's
  own adventure list names no further adventure after this one — moves the
  campaign run to `finished`; no object's position changes either way. Both
  successful outcomes also append a DM-visible `tool_call`,
  `result: "ok"`, and commit once. Full behaviour is
  `docs/modules/playthrough.md` §9.
- `request_player_roll` — derives the formula from `kind` and the actor via
  `dice.derive_formula`, then appends a player-visible `roll_requested`
  event naming the kind, the actor and that formula. No dice are rolled and
  no total exists yet — only the request is on record. Idempotent within
  one `turn_id` (sprint 010/09, ← finding): a LangGraph resume re-executes
  the calling `request_player_roll` tool's coroutine from the top, so this
  call runs a second time before its own `interrupt()` resolves; a second
  call for the same `turn_id`/`actor_id`/`kind` with no `roll` answering it
  yet returns the first call's own event rather than writing a duplicate,
  orphaned one.
- `resolve_roll_request` — answers a `roll_requested` event by id: re-uses
  the formula that event already stored rather than deriving it again,
  rolls it through `dice.roll`, and appends the resulting `roll` event —
  dice, modifier and total — at the same visibility the request carried.
  Idempotent for the same reason `request_player_roll` is (sprint 010/09,
  ← finding): a second call naming a `request_id` that already has a
  `roll` returns that `roll` again rather than rolling twice.
- `roll` — derives, rolls and appends the `roll` event in one call, `dm`
  visibility unless told otherwise; the path for a creature's own roll, or
  any roll the player must not see. Writes its own `roll_requested` event
  first, so the `roll` it appends still points back to a request, exactly
  as `resolve_roll_request`'s does.
- `roll_initiative` — takes two sides, each a list of object ids, and
  nothing else. Per side, the first row that carries a `member_id` goes
  through `request_player_roll(kind="initiative")` — a player's own click
  still decides that side's roll — otherwise the side is rolled outright
  through `roll(..., visibility="player")`, `roll`'s own path above for a
  creature's roll. Writes no row beyond whichever `roll_requested` / `roll`
  events those two calls already write on their own, and no `tool_call` —
  finding out who goes first spends nobody's turn, so there is nothing here
  for a pass or a refusal to be recorded against. Full behaviour is
  `docs/modules/playthrough.md` §20.
- `passive_check` — no dice at all: adds the named ability's modifier to
  `10` and weighs the result against `dc`, returning the pass/fail outcome
  directly and appending one DM-visible `tool_call` event carrying that
  outcome, with no `faces` anywhere in it.
- `ask_player` — appends a player-visible `question` event carrying the
  text asked and the options offered; the next `player_action` is expected
  to answer it.
- `resolve_check` / `resolve_save` — turn a roll id into pass or fail
  against a `dc`, each resolving the roll's own run and checking membership
  before anything else, the same way `use_exit` resolves a run from an
  actor id. A `dc` outside `5..30` is refused (`InvalidDcError`,
  `INVALID_DC`) before the roll is even looked at. Otherwise each asks the
  shared `_consume_roll` for the one kind it is allowed to spend —
  `resolve_check` for `ability_check`, `resolve_save` for
  `saving_throw` — an unknown roll id answering `NOT_FOUND`, anything else
  `_consume_roll` refuses answering `RollNotUsableError` /
  `ROLL_NOT_USABLE`; a `custom` roll is refused by both, unconditionally,
  since its kind never matches either. Found and unspent, they weigh the
  roll's stored `total` against `dc`, append one DM-visible
  `tool_call {name, args: {rollId, dc}, rollIds: [rollId], result: "ok",
  outcome: {total, dc, success}}`, commit once, and return
  `outcome.success` — pass or fail lives here, never on the `roll` event
  itself. Every refusal is recorded first — its own `tool_call`,
  `result: "refused"`, naming the roll and the reason — and committed on
  its own before the error is raised, exactly as `_refuse_exit` does, so a
  mistaken attempt never erases the record of itself and never spends the
  roll it was refused for.
- `_consume_roll` — internal; the one place that decides whether a roll may
  be spent, reading `events` alone rather than a consumption column: the
  named roll id must be a `roll` event on this run, its payload `kind` must
  match what the caller asks for, its `turn_id` must equal the caller's
  (both `NULL` counts as a match), and no `tool_call` already on this run
  and turn may carry `result: "ok"` with this id in `rollIds`. Any of those
  failing raises `RollNotUsableError`; nothing about the roll is written
  either way — only the caller above records a refusal.
- `interact` — the one mechanic that acts on a fixture's own authored
  checks (`FixtureTemplate.checks`, `docs/modules/content.md`): takes the
  actor, the object, which of the object's checks is being attempted (by
  the check's own `action` text, matched exactly) and an optional roll id.
  Loads the actor and the object by id (`NOT_FOUND` otherwise), requires
  the run `ready` or `active`, then runs the one-action check every
  action-spending mechanic shares (§17 below) before ever matching the
  attempt against the object's checks — a creature that has already acted
  this turn is refused (`AlreadyActedError`, `ALREADY_ACTED`) before
  its attempted action is even looked up. No check on the object matching
  the named action at all is `ActionNotAvailableError` /
  `ACTION_NOT_AVAILABLE`. Given a roll id, it spends it through the same
  `_consume_roll` `resolve_check` and `resolve_save` already share for
  `ability_check` — a roll of the wrong kind, already spent, from another
  turn or of the `custom` kind answers `RollNotUsableError` /
  `ROLL_NOT_USABLE` exactly as it does there — and passes when the roll's
  stored `total` meets the check's own `dc`. Given no roll id, it passes
  instead when a row with `owner_object_id` equal to the actor's id carries
  a `template_id` the check's own `bypassed_by` names; carrying nothing
  that bypasses it, with no roll either, is `RollRequiredError` /
  `ROLL_REQUIRED`. A passing check also appends a player-visible
  `way_opened {actorId, actorName, objectId, objectName, action}` (sprint
  010/04, I2) before the `tool_call` below — `action` is the authored
  string verbatim, never the model's own words; a failed check changed
  nothing in the world and appends no such row, though its `tool_call`
  still records `ok`. Either pass appends one DM-visible
  `tool_call {args: {actorId, objectId, action, rollId?},
  rollIds: rollId ? [rollId] : [], result: "ok",
  outcome: {action, dc, total?, bypassedBy?, success: true}}` and commits
  once — `objects` is never written by this function; the check's authored
  `success` text is the Dungeon Master's own prose to narrate, never a
  state flip this function makes. A refusal is recorded first — its own
  `tool_call`, `result: "refused"`, naming the actor, the object and the
  action — and committed on its own before the error is raised, the same
  pattern `_refuse_exit` and `resolve_check`'s own refusal already keep.
  Full behaviour is `docs/modules/playthrough.md` §16.
- `take` — the one mechanic that puts an item in an actor's hands: sets
  `owner_object_id` to the actor and clears its position
  (`adventure_run_id`, `scene_id` both `NULL`, §6). Loads the actor and the
  item by id (`GameObjectNotFoundError` otherwise), requires the run
  `ready` or `active`, then runs the same one-action check `interact`
  shares (§17) before reach is even considered. Reachable means the item
  lies, unowned, in the actor's own scene, **or** its owner is a
  non-creature object standing there too — a container, which is how
  `stolen-fleece` comes out of `wool-sack` in Greenhollow (AC5); an item
  another *creature* carries is not reachable this way, nor is one in
  another scene, nor is any of this true of an actor with no scene at all.
  Anything else is `ObjectNotReachableError` / `OBJECT_NOT_REACHABLE`. A
  pass also appends a player-visible `item_moved {movement: "taken",
  actorId, actorName, itemId, itemName}` (sprint 010/04, I2) before the
  `tool_call` below, naming actor and item by their stored `name`s, never a
  tool argument, then appends one DM-visible `tool_call {args: {actorId,
  itemId}, result: "ok"}` and commits once; a refusal is recorded the same way,
  `result: "refused"`, on its own commit, before the error is raised —
  the pattern `_refuse_exit` and `interact`'s own refusal already keep.
  Full behaviour is `docs/modules/playthrough.md` §18.
- `drop` — the reverse of `take`: clears `owner_object_id` and gives the
  item the actor's own position instead. Free — it does not run the
  one-action check at all, following the SRD's ruling that letting go of
  what you carry costs nothing. Otherwise the same shape: actor and
  item loaded by id, the run required `ready` or `active`, an item the
  actor is not carrying refused as `ObjectNotReachableError` /
  `OBJECT_NOT_REACHABLE`. A pass also appends a player-visible
  `item_moved {movement: "dropped", actorId, actorName, itemId, itemName}`
  (sprint 010/04, I2) before the `tool_call` below; a pass or a refusal
  each its own committed `tool_call {args: {actorId, itemId}}`. Full
  behaviour is `docs/modules/playthrough.md` §18.
- `give` — moves an item from one creature's hands straight to another's:
  re-owns it from `from_id` to `to_id`, touching no position column at all.
  Loads both creatures and the item by id, requires the run `ready` or
  `active`, runs the one-action check (§17), then reach: the item must
  already be carried by the giver, and the receiver must be a creature
  standing in the giver's own scene — anything else, including the two
  creatures in different scenes, is `ObjectNotReachableError` /
  `OBJECT_NOT_REACHABLE`. A pass also appends a player-visible
  `item_moved {movement: "given", actorId, actorName, itemId, itemName,
  toId, toName}` (sprint 010/04, I2) before the `tool_call` below —
  `toId`/`toName` name the receiver and are set only for this movement —
  then appends one DM-visible
  `tool_call {args: {actorId, toId, itemId}, result: "ok"}` and commits
  once — `actorId` names the giver, so one key always names who acted; a
  refusal keeps the same shape, `result: "refused"`, committed on its own
  before the error is raised. Full behaviour is
  `docs/modules/playthrough.md` §18.
- `use_item` — the seam where using an item will one day work, and today
  refuses every template unconditionally: `ItemTemplate`
  (`content/schemas.py`) carries no field yet that could say an item is
  consumable, so there is nothing for this mechanic to do but refuse.
  Loads the actor and the item by id, requires the run `ready` or
  `active`, runs the one-action check (§17) before the refusal itself, so
  a creature that has already acted is turned away by `AlreadyActedError`
  rather than by the seam underneath it, then always raises
  `ItemNotConsumableError` / `ITEM_NOT_CONSUMABLE` — recorded first as its
  own DM-visible `tool_call {args: {actorId, itemId, targetId?},
  result: "refused"}`, committed on its own, exactly like every other
  refusal in this module. Full behaviour is
  `docs/modules/playthrough.md` §19.
- `attack` — the sixth action-spending mechanic: names the actor, the
  target, an optional item (absent when a monster's own stat block
  supplies the attack instead, §13) and the roll made for it. Loads the
  actor and runs the same one-action check every action-spending mechanic
  shares (§17), then loads the target and, when named, the item, refusing
  `ObjectNotReachableError` / `OBJECT_NOT_REACHABLE` — the same code `take`,
  `drop` and `give` already raise (§18) — when the target is in another
  scene or the item is not the actor's own to swing. Spends the named roll
  through `_consume_roll(kind="attack")` exactly as `resolve_check` and
  `resolve_save` do (§14), refusing `RollNotUsableError` / `ROLL_NOT_USABLE`
  for a roll of the wrong kind, already spent, or from another turn. An
  attack is always one d20: the roll's own recorded die decides a
  **critical hit** on a natural 20 whatever the target's armour; short of
  that, the roll's total reaching `armour_class` is a **hit**, falling
  short a **miss** — settled and written on the attack's own `tool_call`,
  never on the roll (← D11). Writes no row anywhere else. A pass appends
  one DM-visible `tool_call {args: {actorId, targetId, itemId?, rollId},
  rollIds: [rollId], result: "ok", outcome: {outcome, total, natural,
  armourClass}}` and commits once; a refusal keeps the same shape,
  `result: "refused"`, committed on its own before the error is raised,
  the pattern every refusal in this module already keeps. Full behaviour
  is `docs/modules/playthrough.md` §21.
- `damage` — binds a wound to the blow that landed it: takes a `damage`
  roll and a **hit id**, the event id of an `attack` `tool_call`, and reads
  its target from that entry rather than from any argument, refusing
  `HitNotUsableError` / `HIT_NOT_USABLE` — a code of its own, apart from
  `ROLL_NOT_USABLE` (§14), because a hit failing is a different mistake
  from a roll failing — unless that entry is on this run, is an `attack`
  that succeeded `hit` or `crit`, belongs to this turn, names this same
  target, and has not already been paid out by an earlier `damage` call.
  Then spends the `damage` roll through the shared `_consume_roll` like
  every other roll (§14) and applies `min(total, current_hp)`, clamped at
  `0`, never below. At `0`, a row with no `member_id` becomes
  `is_alive = False`; a character's row keeps `is_alive = True` and instead
  gets its whole `state` reassigned with `down: True` added — a new
  `CharacterState` field, alongside `abilities`, `race`, `character_class`,
  `background` and `appearance` — since this JSONB column is never edited
  in place. Makes no one-action check of its own: the `attack` it is bound
  to already spent that. A pass also appends a player-visible
  `hp_changed {targetId, targetName, before, after, maxHp, alive, down}`
  (sprint 010/04, I2) before the `tool_call` below — `before`/`after`
  bracket the hit points actually applied, `alive`/`down` the same flags
  the `tool_call` itself records — then appends one DM-visible
  `tool_call {args: {targetId, rollId, hitId}, rollIds: [rollId],
  result: "ok", outcome: {rolled, applied, currentHp, isAlive, down}}` and
  commits once; a refusal keeps the same shape, `result: "refused"`,
  committed on its own before the error is raised. Full behaviour is
  `docs/modules/playthrough.md` §22.
- `get_awaiting` — reads a run's open turn back from `events` alone and
  answers `"none"`, `"roll:<eventId>"` or `"answer:<eventId>"`: the id of
  the newest `roll_requested` with no `roll` event answering it yet, else
  the newest `question` with no `player_action` after it, else `"none"`.
  No column records this; the same three-way answer is derived again on
  every call. Called by the events route (below), never on its own.
- `open_turn_id` (sprint 010/03) — the run's open turn id alone: whichever
  `turn_id` its newest event carries, or `None` when there is no event yet
  or the newest one carries no turn. `game.service.run_turn` calls this to
  reuse the open turn's id across a resumed interrupt leg (an answered
  question, a resolved roll, a retried mid-flight break) instead of
  minting a new one.
- `_require_member` — internal; every function above that takes a run id
  calls it first to check membership before doing anything else.
- `_require_writable` — internal; raises `RunArchivedError` when the run is
  `archived`. Called by `rename_campaign_run`, `create_character`,
  `enter_adventure` and `use_exit` before they touch anything.
- `append_event` — the **only** function in the tree that writes to
  `events`. Takes the run, `type`, `visibility`, a payload (dict or the
  type's own payload model), and optionally `turn_id`, `actor_member_id`
  and a `core.llm.service.Usage`. Validates the payload against
  `EVENT_PAYLOADS[type]`, the sixteen-entry registry in `schemas.py`
  (`narration`, `player_action`, `roll_requested`, `roll`, `question`,
  `tool_call`, `scene_entered`, `adventure_started`, `adventure_completed`,
  `system`, `error`, `warning`, plus `item_moved`, `hp_changed`,
  `way_opened` and `rule_looked_up`, added in sprint 010/04), and stores it
  `model_dump(by_alias=True)`.
  An unknown type or visibility, or a payload that fails its type's shape,
  raises `InvalidEventPayloadError` and writes nothing. `usage.cost_usd`
  becomes `Decimal(str(...))`, never `Decimal(float)`. `add`s and `flush`es
  so the new id exists — **never commits**; the caller commits once, so the
  event and the state change it describes land together or not at all. No
  membership check — every caller has already made one. A non-blank
  `narration` is also embedded through `core.llm.service.embed_texts`
  (off the event loop via `asyncio.to_thread`) before the row is built: on
  a right-width vector the columns and `get_settings().embedding_model`
  are stored and the embedding's own usage is added on top of the
  caller's `prompt_tokens`/`cost_usd`; any failure or wrong-width vector
  leaves both columns `NULL`, logs one `warning` and never raises, so a
  lost embedding never loses the narration. Every other event type never
  calls the seam.
- `record_rule_lookup` (sprint 010/04, I3) — the module's ordinary mechanic
  shape, `_require_member` then append then commit, for a rule lookup that
  matched something: appends a player-visible `rule_looked_up {topic}`,
  `topic` being the best match's own `heading_path`, supplied by the
  `lookup_rule` tool only when its search matched. No refusal path — a
  lookup that matched nothing never calls this at all, so there is nothing
  here to refuse.
- `list_events` — the caller's `player`-visible events for a run, ordered by
  `id`, `after` exclusive, `limit` capped at 500 (default 200). Checks
  membership; `dm`-visible rows are excluded, not merely hidden downstream.
- `latest_event_id` — the highest `id` among a run's events, or `None`.
  Checks membership. The only function the stream endpoint below calls on
  every poll.
- `run_cost` — `SUM(cost_usd)` over the run's events, whole and grouped by
  `turn_id` (the `NULL`-turn group last), both as `Decimal`, never a float.
  Checks membership like every other read. Called only from the `app
  playthrough cost` CLI command below — no route calls it, and none is
  meant to.
- `recap` — a run's `n` most recent `narration` events (default 5), oldest
  first, no question asked. An operator read gated on the run's existence
  alone, not membership: `_get_run` first, no `user_id`. Picks the newest
  `n` by `id DESC LIMIT n`, then flips to chronological order in Python —
  no `embedding IS NOT NULL` filter and no call to the embedding seam at
  all. A run with no narration returns `[]`. Reads into `NarrationRead`
  (`id, createdAt, text`) — deliberately not `EventRead`.
- `recall` — the `k` (default 5) `narration` events from anywhere in the
  run whose meaning is closest to a `query`, closest first, no relevance
  floor. Same operator gate as `recap` (`_get_run`, no `user_id`). Embeds
  `query` exactly once through `llm_service.embed_texts`, off the event
  loop; any seam failure propagates unchanged, unlike a write. Orders
  `narration` rows with `embedding IS NOT NULL` by
  `Event.embedding.cosine_distance` — the same predicates and operator
  the `ix_events_embedding_narration` partial index serves, so a row that
  failed to be encoded is never a candidate. A run with no narration
  returns `[]`. Reads into `NarrationRead` like `recap`.

Cost has **no HTTP route anywhere in this module, on purpose**: it is a
developer's number, not a player's, meant for a developer drawer the
frontend does not have yet (← D14). Until that drawer exists, the only way
to read it is `app playthrough cost <run-id> --user <user-id>` (Typer,
`commands.py`), which prints the run's total and then one
`turn <turn-id>: <amount>` line per turn (`turn -: <amount>` for the
turnless group), or `f"{exc.code}: {exc}"` to stderr and exit `1` when the
caller is not a member (`NOT_FOUND`). A test asserts no route exposes cost,
so a future endpoint added elsewhere in the app cannot reintroduce it by
accident.

Rolling, and spending a roll once it exists, both have **no HTTP route
either, for the same reason `use_exit` has none**: the only thing meant to
call `request_player_roll`, `resolve_roll_request`, `roll`,
`roll_initiative`, `passive_check`, `ask_player`, `resolve_check` or
`resolve_save` is the Dungeon Master's own tool layer, a later phase's
work. Until that layer exists, `app
playthrough roll <kind> --actor <object-id> --user <user-id>` (Typer,
`commands.py`) exercises the same derivation and roll from the
terminal — one flag per context key the chosen kind needs (`--ability`,
`--item`, `--attack`, or `--expression` for `custom`) — and prints the
kind, the actor, the formula, the dice, the modifier and the total, or
fails exactly like `app playthrough cost` does on a bad expression: the
offending text to stderr and exit `1`. Spending a roll has no CLI command
of its own yet — nothing outside the test suite calls `resolve_check` or
`resolve_save` today.

`app playthrough narrate <run-id> "<text>" [--player-action]` (Typer,
`commands.py`) is an operator command with no membership gate, like `app
srd status`: no `--user`. It writes one `narration` event, or one
`player_action` event with `--player-action`, both `player`-visible and
carrying `{"text": <text>}`, through `append_event` — the module's one
writer — commits, and prints `event: <id>`. A refusal from `append_event`
fails exactly like `cost` and `roll` do: `f"{exc.code}: {exc}"` to stderr
and exit `1`. An unknown run id is not caught here — `append_event` does
no run lookup — and surfaces as the database's own error instead.

`app playthrough recall <run-id> "<query>" [--k]` and `app playthrough
recap <run-id> [--n]` (Typer, `commands.py`) are the CLI reads over the
run's remembered narration: `recall` finds entries by *meaning* — it
searches with an embedding of `<query>` and returns the `k` (default 5)
closest — while `recap` is recency alone — the `n` (default 5) most
recent entries, oldest first, no query. Both are operator commands with
no membership gate, like `narrate`: no `--user`. Each prints one line per
entry — `<id> <time> <text>` — and nothing else; no matches or no
narration yet prints nothing and exits `0`. An unknown run fails exactly
like every other command here: `f"{exc.code}: {exc}"` to stderr and exit
`1` (`NOT_FOUND`) — the lookup lives in `recall`/`recap` themselves, not
in the command.

**Interacting, taking, dropping, giving, using an item, attacking and
dealing damage all have no HTTP route either, for the same reason**:
`interact`, `take`, `drop`, `give`, `use_item`, `attack` and `damage` are
meant to be reached by the Dungeon Master's own tool layer, not called
directly, and none has a CLI command of its own either — nothing outside
the test suite calls any of them today. Neither does `roll_initiative`,
for the same reason as every other roll above.

**One action per creature per turn** is a rule `interact` keeps and
`take`, `give`, `use_item` and `attack` all share — five actions in all,
the full set §17 names. `damage` makes no one-action check of its own: the
`attack` it is bound to has already spent the turn. Dropping, using an
exit, rolling, resolving a roll and rolling for initiative are outside
that set on purpose: dropping is free per the SRD, and the other four were
never a creature acting on something to begin with. The check itself reads
`events` for this run and this creature's turn — its `tool_call` rows
already marked `result: "ok"` for one of the action-spending names above,
naming this actor in `args.actorId` — and refuses with
`AlreadyActedError` / `ALREADY_ACTED` the moment one is found; nothing
about it is stored on the creature, the turn or anywhere else, so a fresh
`turn_id` always starts the count at zero again and a refused attempt,
recorded but never `"ok"`, is never counted against it. Full behaviour is
`docs/modules/playthrough.md` §17.

The stream (`GET …/stream`, above) polls `service.latest_event_id` on an
interval, sends the `updated` message when it has changed since the last
tick or a keepalive when it has not, and ends the generator on
`await request.is_disconnected()`, on
`GeneratorExit`, or once `sse_max_lifetime_seconds` has elapsed since the
stream opened — whichever comes first; each tick rolls back rather than
holding a transaction open. Both `sse_poll_interval_seconds` (default `2.0`)
and `sse_max_lifetime_seconds` (default `300.0`) are settings, read inside
the handler rather than at import time, so a test can pin them small. There
is no background worker and nothing subscribes to the database for
changes — the handler polls, which is enough at this size. A client whose
connection ends this way simply reconnects, as any server-sent event stream
does; nothing on the server distinguishes that reconnect from a first
connection.

Every service function takes the acting user and checks membership before
touching a run, except `append_event`, which every one of its callers has
already checked on the caller's behalf. A run belonging to someone else and
a run that does not exist answer identically — not found — so no one can
probe for the existence of another player's game. Errors: an unknown or
foreign run, an unknown campaign, an actor or object id `use_exit`,
`interact`, `take`, `drop`, `give`, `use_item`, `attack` or `damage`
cannot find, and a roll id no consumer recognises are not found; a hit id
no consumer recognises is *not usable*, not *not found*; a
run already started, a second character, an archived run refusing a
write, an invalid status transition, a second adventure entered while one
is active, entering with none left to enter, `use_exit` asked for an exit
it will not take, spending a roll already spent, from a later turn, or of
the wrong kind, resolving against a `dc` outside `5..30`, `interact` asked
for an action its object never authored, asked for a check needing a roll
with none given and nothing carried that bypasses it, a second action
asked of a creature that has already spent this turn's, `take`, `drop`,
`give` or `attack` asked to reach an item or a target that is not
reachable from where the actor stands, `use_item` asked to use anything
at all, and `damage` asked to spend a hit that missed, belongs to another
turn, names a different target, or has already been paid out are each a
domain conflict (`ALREADY_STARTED`, `CHARACTER_EXISTS`, `RUN_ARCHIVED`,
`INVALID_RUN_STATUS`, `ADVENTURE_ACTIVE`, `ADVENTURE_EXHAUSTED`,
`EXIT_NOT_AVAILABLE`, `ROLL_NOT_USABLE`, `INVALID_DC`,
`ACTION_NOT_AVAILABLE`, `ROLL_REQUIRED`, `ALREADY_ACTED`,
`OBJECT_NOT_REACHABLE`, `ITEM_NOT_CONSUMABLE`, `HIT_NOT_USABLE`); a
payload not matching its type's shape is a validation error
(`InvalidEventPayloadError`).

**The transcript read sorts by `id` alone, and that is only safe because one
process mints every id.** `id` is a ULID, chronological by construction, but
that ordering is guaranteed only within one generating process's clock —
ids from two different processes carry no ordering guarantee against each
other in the same millisecond. This backend runs as a single process today,
so the read's `ORDER BY id` is always correct; the fix if that ever changes
is a database-issued sequence, not built now because it is not yet needed.
The full reasoning, for whoever adds a second process, lives in
`docs/modules/playthrough.md` §10.
