---
author: sprint
owner: agent
created: 2026-09-24
---
# Plan: Sprint 02

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | Initiative is one hero-side roll and one automatic hostile-side roll settled once into a typed result with a stable order, hero side winning a tie (I1); the old monolithic initiative and its tests are gone; the old `roll_initiative` tool keeps working and additionally reports the order | two rolls per fight; tie goes to the hero side; order is stable and winner-first | – |
| 2 | backend-python | Attack returns a typed hit/miss/critical result carrying the hit id; damage returns a typed result and doubles only the dice on a critical, flat modifier once (I2); the old attack and damage tools read the typed results instead of scanning events | normal hit through damage; miss; critical doubles dice, modifier once; damage to 0 hp reports down | – |
| 3 | backend-python | One down-state rule used by every mutation and read: a hero at 0 hp is downed, not alive for eligibility, excluded from actor resolution and the live-creature hint, and reads report `down` beside `is_alive` (I3) | a downed hero is reported down by scene, card and actor lookup and cannot be resolved as a target or actor | WI2 |

## Interfaces
- I1 (playthrough/schemas.py, internal dataclass; service signatures):
  ```python
  @dataclass(frozen=True)
  class InitiativeResult:
      hero_total: int; hostile_total: int
      hero_roll_id: str; hostile_roll_id: str
      winning_side: Literal["hero", "hostile"]   # tie -> "hero"
      order: list[str]                            # stable actor ids, winner side first
  async def roll_side_initiative(db, *, user_id, run_id, hero_ids, hostile_ids, turn_id=None) -> tuple[Event, Event]
  async def settle_initiative(db, *, user_id, run_id, hero_ids, hostile_ids, turn_id=None) -> InitiativeResult
  ```
- I2 (same file; `attack` signature otherwise unchanged; `damage` gains `critical`):
  ```python
  @dataclass(frozen=True)
  class AttackResult:
      status: Literal["hit", "miss", "critical"]
      hit_id: str | None                          # tool_call event id; None on miss
      total: int; natural: int; armour_class: int
  @dataclass(frozen=True)
  class DamageResult:
      applied: int; current_hp: int; max_hp: int
      is_alive: bool; down: bool
  async def attack(...) -> AttackResult
  async def damage(..., critical: bool = False) -> DamageResult
  def dice.derive_formula(..., context={"critical": True}) -> str   # doubles dice only, modifier once
  ```
- I3: `def is_down(obj: GameObject) -> bool` — member at 0 hp, or `not is_alive`; `describe_scene_creatures` and `character_read` add `down` alongside `is_alive`; `resolve_actor_ref` and the live-creature hint exclude downed actors.

## Acceptance tests (qa)
No qa agent (owner: reduce testing); WI tests cover AC1–AC4 directly, AC4's "terminal game still runs a fight" is covered by the unchanged game suite.

## Order
Parallel: WI1, WI2. Then: WI3.
