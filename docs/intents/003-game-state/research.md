---
author: fhit:architect
owner: agent
created: 2026-09-16
---
# Research: intent 003 — Game State

## Facts

**What exists.** Two tables — `users`, `sessions` (`backend/alembic/versions/0001_baseline.py`); linear
revision chain, one `env.py` import per module (`alembic/env.py:13`-`14`), deterministic constraint names
(`core/db.py:19`-`25`). `ID_TYPE = CHAR(26)` + `generate_id()` (`app/core/ids.py:12`-`17`) is the only way to declare
an id; cascade precedent is `sessions.user_id` (`auth/models.py:17`-`19`), user reached via `auth/dependencies.py`.
Async SQLAlchemy, services own `commit` (`core/db.py:42`); the suite never builds an engine and stubs `get_db_session`
(`backend/tests/conftest.py:1`-`14`), but **SRD has since shipped a scratch-database fixture**
(`backend/tests/srd/conftest.py`) that D15 promotes to a shared one: accept/refuse criteria run as
`@pytest.mark.database` tests under `make backend-test-db`, `make backend-test` staying `--no-deps`. `modules/game/`
holds only `prompts/v1/system/`: no game table.

**What phase 1 authored**, so "instantiated from content definitions" is concrete: campaign
`backend/content/campaigns/greenhollow/v1/`, one adventure, 4 scenes, entry `village-green`; 9 campaign-scoped
`object_templates`, **13 instances** across `placements[]` — 3 carried (e.g. `wool-sack`→`stolen-fleece`), one
placement with `count: 3`; loader `content/service.py:51`-`73`,`:319`,`:330` (`load_campaign` → `LoadedCampaign`).
Promotable fields exist on creatures only — `StatBlock.max_hp`/`armour_class` (`content/schemas.py:29`-`34`); item
and fixture templates carry neither (`:50`,`:62`), the seed character flat (`:116`-`125`). A run start is ~14 rows.

**The docs already rule** (`docs/general/model.md`) ULID keys, content pinned as `v<n>`, one generic `objects`
table with four promoted nullable columns, carried objects as own rows via `owner_object_id`, position on the player's
creature, settings on the run, ownership on a membership row, events vs journal split — but four points were open and
are closed here: ownership (`roadmap/Stage-01/README.md:315`), progress (`:316`), placement (`:317`), event cost
(`:318`). **D1–D9 have since landed** and bind everything below; the full schema is `decisions/model.md`.

**External** (docs-lookup 2026-09-16, context7 `/websites/sqlalchemy_en_20`): SQLAlchemy 2.0.52, Alembic
1.19.2, psycopg 3.3.5, pydantic 2.13.5, python-ulid 4.0.1 (`backend/uv.lock`). `postgresql.JSONB` maps through
`mapped_column`, but **in-place mutation of a JSON dict is not seen by the unit of work** — reassign the whole
attribute (cheaper, and what `model.md`'s per-`kind` Pydantic rule forces) or use `MutableDict.as_mutable()`.

## Options

**1 — Run and pin.** `campaign_runs(id, campaign_id, content_version, title, status, created_at, updated_at)` —
two plain string columns mirroring the loader's own `(campaign_id, version)` argument pair, indexable, no FK on
`campaign_id` (loader-validated, `model.md:47`); `status` ∈ `active|archived|finished` (D3), nullable `title` (D11),
no purge state (§5 fences it out, `README.md:254`). *Rejected:* resolving the latest version at read — an edit would
then mutate a save in progress, which `model.md:32` exists to prevent.

**2 — Progress and position** (closes `:316`; **decided by D10, D12 and D13**, which uphold `model.md` on both counts
and overrule the single-table recommendation this file previously carried). Two levels: `campaign_runs` is the
container, `adventure_runs` holds one row per adventure entered with its `status`, and the schema is prepared for
several adventures from the start. **Position stays on the creature (D12)** — splitting the party is normal play, so
there is no party position — and is the pair `(adventure_run_id, scene_id)` on the object row, because a scene id is
unique only inside its adventure file. Provenance (`source_adventure_id`, `source_scene_id`) is kept separate from
position, since objects are instantiated eagerly before their adventure is entered. A player character is an object
with `member_id` set; **D13 forbids any unique index on it**, so several characters per member are a legal state. The
active adventure is derived (`status = 'active'`, one per campaign run by partial unique index). Full argument:
`decisions/model.md` §3.

**3 — Object state.** One generic `objects` table promoting exactly `current_hp, max_hp, armour_class,
is_alive` (nullable, creature-only) beside structural columns `kind, template_id, instance_key, owner_object_id,
member_id`, the position pair and the two provenance columns; `state` is JSONB, written only after per-`kind` Pydantic
validation and reassigned wholesale. The PC is the creature whose `member_id` is set. Cost: enforcement rests on those
models (`model.md` gap 4). *Rejected:* a table per kind — the database enforces the shape, at three tools and read
paths, item/fixture rows carrying columns the templates never fill.

**4 — Event stream** (closes `:318`). `events(id, campaign_run_id, turn_id, type, visibility, payload,
prompt_tokens, completion_tokens, cost_usd, created_at)`; append-only, ordered by ULID id, `visibility` ∈ `player|dm`;
**cost stored per event**, because `usage_of()` already returns the provider's own figure per call
(`core/llm/service.py:70`-`74`,`:211`). `turn_id` (nullable ULID) groups one turn, so phase 9's per-turn figure is a
`GROUP BY` and the run total a `SUM` — no denormalised total. *Rejected:* recomputing from tokens × a price table —
new owner-only `.env.dist` config, and old runs re-price themselves as prices drift; a separate `event_costs` table —
a 1:1 join on every trace read, for three integers.

**5 — Settings, ownership, placement.** Settings: nullable `model`, `temperature`, `personality_prompt_id`,
`system_prompt_override` on `campaign_runs`, NULL in Stage-01 per D6 — a 1:1 table buys a join and no lifecycle, a
JSONB bag defers validation of four known fields. Ownership (closes `:315`, upholding `model.md`):
`campaign_run_members(id, campaign_run_id, user_id, role, created_at)` unique on `(campaign_run_id, user_id)`, no
owner column — a `user_id` on the run saves one indexed join but re-opens every phase-5 authorisation path and drops
the concession `architecture.md:23` states. Placement (closes `:317`): one `modules/playthrough/` (D14) owns the five
tables **and** phase 5's transitions — `users`/`auth` set the precedent that a module owns its own rows plus the code
writing them (`modules/*/README.md`), and a state-only module would be the technical layer `architecture.md:101` rules
out. `modules/game/` stays the agent's home and calls `playthrough.service`, never the reverse; the journal is phase
6's.

## Docs this invalidates

`model.md` — `Playthrough` is renamed **campaign run** throughout (D2: 14 occurrences here, 9 across the other general
docs) and `AdventureRun` is **upheld** by D10; the position paragraph moves to the adventure run; the combat
paragraph, Encounter node and lifecycle row are **deferred to phase 8, not dropped** (D8); the Purge row goes (out of
scope, and D3 says nothing is deleted); ownership is upheld, closing both conditional rows (`README.md:385`-`386`).
`glossary.md:16`,`:64` — Encounter and Initiative marked deferred; nothing names the **seed player character** phase 3
instantiates from. `app-vision.md:51` and `architecture.md:78` promise turn order — deferred, not delivered (D8). Plus
`docs/README.md` and a new `docs/modules/playthrough.md`.

## Open questions

D1–D14 answer everything this section once listed — naming, several runs, archiving, what the player sees, resume,
overrides, the version pin, combat, proving a table, the two levels, the title, position, characters, the module.

*product-visible* — none outstanding. *technical* — fifteen numbered proposals await veto in `decisions/model.md`;
D10–D13 added the adventure-run status set, what "this adventure is done" means with characters apart, the
position/carried check, the player-character instance key, and an `actor_member_id` on events.
