---
author: sprint
owner: agent
created: 2026-09-24
---
# Plan: Sprint 04

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | One read returns the whole current moment as typed views (I1): run, adventure, scene, actors with derived roles, health and down state, disposition and hostility, attacks, inventory, fixtures with achieved outcomes, exits with conditions, authored facts, consequences, hidden facts, and a bounded recent transcript window; a public view strips hidden facts, difficulties and private intent; broken content raises | a rich Greenhollow scene has every field; the public view carries no secret, DC, ability/skill or NPC intent; a broken scene raises | – |
| 2 | backend-python | Recall of older play returns, for each semantic match, that turn's player-visible events (I2); the existing recall and its tool are untouched | a fact older than the recent window comes back with its turn's player action and narration | I1's `RecentEvent` only |

## Interfaces
- I1 `backend/app/modules/playthrough/situation.py`, frozen dataclasses (never a wire shape):
  ```python
  RECENT_WINDOW = 20
  Role = Literal["hero", "ally", "hostile", "neutral"]
  class AttackView: name: str; to_hit: int; damage: str
  class ItemView: id: str; name: str
  class ActorView: id; name; role: Role; kind: str; current_hp; max_hp; armour_class; is_alive: bool; down: bool; disposition: str | None; hostile: bool; attacks: tuple[AttackView, ...]; inventory: tuple[ItemView, ...]
  class FixtureCheckView: action: str; ability: str; skill: str | None; dc: int; success: str      # private only
  class FixtureView: id; name; description; checks: tuple[FixtureCheckView, ...]; outcomes: Mapping[str, str]   # achieved action -> success prose
  class ExitView: id; kind: str; to: str | None; description; condition: str | None
  class SecretView: fact; ability; skill: str | None; dc: int; discovered_by: str                  # private only
  class RecentEvent: id: str; turn_id: str | None; type: str; payload: Mapping[str, Any]; created_at: datetime
  class Situation:   # private view
      run_id; hero_id; adventure_run_id; scene_id; campaign_title; adventure_title; scene_title
      truth: tuple[str, ...]; consequences: tuple[str, ...]; pressure: str | None
      npc_intent: str | None; secrets: tuple[SecretView, ...]
      hero: ActorView; actors: tuple[ActorView, ...]; fixtures: tuple[FixtureView, ...]
      loose_items: tuple[ItemView, ...]; exits: tuple[ExitView, ...]; recent: tuple[RecentEvent, ...]
      def public(self) -> SituationPublic
  # SituationPublic = Situation minus secrets, npc_intent, every dc/ability/skill (no FixtureCheckView) and unachieved fixture prose; FixtureView.outcomes stays.
  async def service.get_situation(db, *, user_id: str, run_id: str, recent_limit: int = RECENT_WINDOW) -> Situation
  ```
  Roles derived, never stored: member → hero; `state["hostile"] is True` → hostile; disposition names hostility and attacks present → hostile; attacks present → ally; else neutral.
- I2:
  ```python
  class RecalledTurn: turn_id: str | None; anchor_event_id: str; events: tuple[RecentEvent, ...]
  async def service.recall_history(db, *, user_id: str, run_id: str, query: str, limit: int = 3) -> list[RecalledTurn]
  ```
  Anchors come from the existing `recall`; each distinct turn expands to its player-visible events ordered by id; an anchor without a turn yields only its narration row.

## Acceptance tests (qa)
No qa agent (owner: reduce testing); WI tests cover AC1–AC4.

## Order
Parallel: WI1, WI2 (WI2 defines `RecentEvent` identically if WI1 has not landed it yet, then reconciles).
