---
author: fhit:architect
owner: agent
created: 2026-09-24
---
# Research: sprint 04 — situation and memory

## Facts

Existing reads to reuse, not duplicate:

- `_require_member` (`backend/app/modules/playthrough/service.py:188`) is the membership gate every run-scoped read opens with; `_get_run:342` loads the run row, `_load_pinned:267` returns the `LoadedCampaign` (campaign, adventures, scenes, object templates) for the run's pinned `campaign_id`/`content_version`, or `None` when content fails to load.
- `get_table:563` already anchors current adventure and scene on the **caller's own** hero (`adventure_run_id`, `scene_id`), loads heroes through the member↔object join plus one grouped item query. Reuse that anchoring logic verbatim; `get_situation` must raise where `get_table` degrades to `None`.
- `character_read:422` + `_character_abilities:390` give hero sheet, abilities with modifiers, carried items and `down`; `is_down:402` is the single down rule (dead, or member character with `state["down"]`).
- `describe_scene_creatures:1386` returns per scene creature `id, name, role(player|monster|npc), is_alive, down, current_hp, max_hp, armour_class, attacks(names only)`. `_creature_attack_names:1370` loads the creature's `CreatureTemplate.stat_block.attacks` via `content_service.load_object_template:388` and swallows `ContentError`. The projection needs full `Attack` (`name, to_hit, damage`, `content/schemas.py:34`) and `CreatureTemplate.disposition` (`:57`), so a new template-backed helper is needed; the existing ad-hoc `role` stays for the old tools.
- `resolve_actor_ref:1321` resolves an id/name reference to a run object.
- Runtime state on `GameObject.state` (`models.py:183`): `state["hostile"]` written by `set_hostility:1058`, `state["fixture_outcomes"][action] = {"success", "turnId"}` by `interact:2502`, `state["left_scene"] = {"sceneId","adventureRunId"}` by `leave_scene:1116`.
- Hidden facts and DCs are authored content: `Scene.hidden: list[Secret]` (`content/schemas.py:86,121` — `fact, ability, skill, dc, discovered_by`), `FixtureTemplate.checks: list[FixtureCheck]` (`:66` — `action, ability, skill, dc, success, bypassed_by`), `Scene.truth`, `npc_intent:125`, `consequences:126`, `Exit.condition:110`. `authored_check:1819` is the shared `(ability, skill, dc)` extractor. Everything under `hidden`, every `dc`, `npc_intent` and unachieved `FixtureCheck.success` prose are private.
- `recall:3782` embeds the query once via `llm_service.embed_texts` in a thread, orders `type='narration' AND embedding IS NOT NULL` by `Event.embedding.cosine_distance` and returns `k` `NarrationRead(id, created_at, text)`. It is gated on `_get_run` only. `Event.turn_id` (`models.py:228`) makes turn expansion a second query: `campaign_run_id = run_id AND turn_id = <anchor.turn_id> AND visibility = 'player'` ordered by `id` — exactly `list_events:3556`'s visibility filter.
- `make_load_context`/`_build_game_context` (`backend/app/modules/game/agent/nodes.py:93-232`) today assembles: party HP/AC/alive plus carried items, scene id/title/`truth`/`npc_intent`/exits, non-player scene creatures via `describe_scene_creatures`, loose scene items and fixtures (names only), `get_awaiting:3588`, and `recap:3751` (5 lines) — each inside `try/except: pass`. The projection is a superset and must drop the swallowing.
- Error surface: `CampaignRunNotFoundError` (`playthrough/errors.py:23`) from the membership gate, `ContentError`/`ContentNotFoundError` (`content/errors.py:1,5`) from scene and template loads, and a new `SituationError(PlaythroughError)` for a run with no hero, no adventure or no scene. Raise; never return a partial `Situation` (AC4).

## Work items

- WI1 `get_situation`: new `backend/app/modules/playthrough/situation.py` dataclasses + `service.get_situation`, reusing the reads above; derives roles, loads full attacks and disposition from templates, folds `hostile`/`fixture_outcomes`/`left_scene` in, and appends the bounded recent window (`RECENT_WINDOW = 20`, `list_events`-style player-visible tail of the run). Tests: one rich Greenhollow scene has every field; `public()` carries no secret, DC, `npc_intent` or unachieved outcome prose; a broken scene raises.
- WI2 `recall_history`: new `service.recall_history` reusing `recall` as the anchor plus one turn-expansion query; `recall` and the old `recall` tool untouched. Test: a fact older than the recent window comes back with its turn's player-visible events.

Both are additive and parallel — WI2 reuses only `RecentEvent` from WI1's module.

## Interfaces

`backend/app/modules/playthrough/situation.py`, frozen `@dataclass`es (never a wire shape, so no Pydantic):

```python
RECENT_WINDOW = 20
Role = Literal["hero", "ally", "hostile", "neutral"]

@dataclass(frozen=True)
class AttackView: name: str; to_hit: int; damage: str

@dataclass(frozen=True)
class ItemView: id: str; name: str

@dataclass(frozen=True)
class ActorView:
    id: str; name: str; role: Role; kind: str
    current_hp: int; max_hp: int; armour_class: int
    is_alive: bool; down: bool
    disposition: str | None; hostile: bool
    attacks: tuple[AttackView, ...]; inventory: tuple[ItemView, ...]

@dataclass(frozen=True)
class FixtureView:
    id: str; name: str; description: str
    checks: tuple[FixtureCheckView, ...]        # private only: ability, skill, dc, success
    outcomes: Mapping[str, str]                 # achieved action -> authored success prose

@dataclass(frozen=True)
class ExitView: id: str; kind: str; to: str | None; description: str; condition: str | None

@dataclass(frozen=True)
class SecretView: fact: str; ability: str; skill: str | None; dc: int; discovered_by: str

@dataclass(frozen=True)
class RecentEvent: id: str; turn_id: str | None; type: str; payload: Mapping[str, Any]; created_at: datetime

@dataclass(frozen=True)
class Situation:                 # private view
    run_id: str; hero_id: str; adventure_run_id: str; scene_id: str
    campaign_title: str; adventure_title: str; scene_title: str
    truth: tuple[str, ...]; consequences: tuple[str, ...]; pressure: str | None
    npc_intent: str | None; secrets: tuple[SecretView, ...]
    hero: ActorView; actors: tuple[ActorView, ...]
    fixtures: tuple[FixtureView, ...]; loose_items: tuple[ItemView, ...]
    exits: tuple[ExitView, ...]; recent: tuple[RecentEvent, ...]
    def public(self) -> SituationPublic: ...
```

`SituationPublic` mirrors `Situation` minus `secrets`, `npc_intent`, every `dc`/`ability`/`skill` (no `FixtureCheckView`) and unachieved fixture prose; `FixtureView.outcomes` survives because it is already recorded fact.

Roles are derived, never stored: `member_id is not None → "hero"`; else `state["hostile"] is True → "hostile"`; else `disposition` naming hostility with attacks present → `"hostile"`; else attacks present → `"ally"`; else `"neutral"`.

```python
async def get_situation(db, *, user_id: str, run_id: str, recent_limit: int = RECENT_WINDOW) -> Situation
async def recall_history(db, *, user_id: str, run_id: str, query: str, limit: int = 3) -> list[RecalledTurn]

@dataclass(frozen=True)
class RecalledTurn: turn_id: str | None; anchor_event_id: str; events: tuple[RecentEvent, ...]
```

`recall_history` calls `recall(db, run_id=run_id, query=query, k=limit)` for anchors (after its own `_require_member`), then one query per distinct `turn_id` for `visibility='player'` events ordered by `id`; an anchor with `turn_id is None` yields a `RecalledTurn` holding only the narration row. The old `recall` tool (`game/agent/tools.py:968`) keeps calling `service.recall` unchanged.

## Open questions

None product-visible.
