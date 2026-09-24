"""The one-shot projection of a run's current moment (sprint 011/04, WI1) --
everything the DM agent's own context and any future player-facing read
need about where the hero stands right now: the scene's authored truth,
its present actors with derived roles, its fixtures and their recorded
outcomes, its exits, its hidden facts, and a bounded tail of recent
transcript. `Situation` is the private view a DM-side caller gets;
`Situation.public()` strips everything a player must never see (intent
§2.1-§2.3, §2.5).

Frozen dataclasses throughout -- never a wire shape, never Pydantic: this
is an internal projection, assembled once per call and hung on nothing a
caller could mutate back into the world.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Literal

RECENT_WINDOW = 20

Role = Literal["hero", "ally", "hostile", "neutral"]

# Substrings an authored `disposition` names friendliness with, when no
# `state["hostile"]` flag has ever been set: an armed stranger defaults to
# `hostile` (← verifier, WI1 round 1 -- Greenhollow's own goblins never
# name hostility in their prose, only cowardice and ruthlessness, so a
# word list for *hostile* missed every one of them), and this is the one
# way its disposition can talk that default back down to `ally` instead.
_FRIENDLY_DISPOSITION_WORDS = ("friendly", "ally", "allied", "helpful", "protective of the party")


@dataclass(frozen=True)
class AttackView:
    name: str
    to_hit: int
    damage: str


@dataclass(frozen=True)
class ItemView:
    id: str
    name: str


@dataclass(frozen=True)
class ActorView:
    id: str
    name: str
    role: Role
    kind: str
    current_hp: int
    max_hp: int
    armour_class: int
    is_alive: bool
    down: bool
    disposition: str | None
    hostile: bool
    attacks: tuple[AttackView, ...]
    inventory: tuple[ItemView, ...]


@dataclass(frozen=True)
class FixtureCheckView:
    """Private only: an unachieved authored check, mechanics and all."""

    action: str
    ability: str
    skill: str | None
    dc: int
    success: str


@dataclass(frozen=True)
class FixtureView:
    id: str
    name: str
    description: str
    checks: tuple[FixtureCheckView, ...]
    outcomes: Mapping[str, str]


@dataclass(frozen=True)
class ExitView:
    id: str
    kind: str
    to: str | None
    description: str
    condition: str | None


@dataclass(frozen=True)
class SecretView:
    """Private only: authored hidden fact, mechanics and all."""

    fact: str
    ability: str
    skill: str | None
    dc: int
    discovered_by: str


@dataclass(frozen=True)
class RecentEvent:
    id: str
    turn_id: str | None
    type: str
    payload: Mapping[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class SituationPublic:
    """`Situation` minus everything a player must never see: `secrets`,
    `npc_intent`, every fixture check (ability/skill/dc/unachieved
    success prose) -- `FixtureView.outcomes` survives, since it is
    already recorded fact, not a hint about what unlocks it."""

    run_id: str
    hero_id: str
    adventure_run_id: str
    scene_id: str
    campaign_title: str
    adventure_title: str
    scene_title: str
    truth: tuple[str, ...]
    consequences: tuple[str, ...]
    pressure: str | None
    hero: ActorView
    actors: tuple[ActorView, ...]
    fixtures: tuple[FixtureView, ...]
    loose_items: tuple[ItemView, ...]
    exits: tuple[ExitView, ...]
    recent: tuple[RecentEvent, ...]


@dataclass(frozen=True)
class Situation:
    """The private, DM-side view (WI1, I1)."""

    run_id: str
    hero_id: str
    adventure_run_id: str
    scene_id: str
    campaign_title: str
    adventure_title: str
    scene_title: str
    truth: tuple[str, ...]
    consequences: tuple[str, ...]
    pressure: str | None
    npc_intent: str | None
    secrets: tuple[SecretView, ...]
    hero: ActorView
    actors: tuple[ActorView, ...]
    fixtures: tuple[FixtureView, ...]
    loose_items: tuple[ItemView, ...]
    exits: tuple[ExitView, ...]
    recent: tuple[RecentEvent, ...]

    def public(self) -> SituationPublic:
        """Strips secrets, `npc_intent` and every fixture's checks --
        `FixtureView.outcomes` alone survives per fixture, since a
        recorded outcome is already fact the player has seen happen."""
        public_fixtures = tuple(
            replace(fixture, checks=()) if fixture.checks else fixture for fixture in self.fixtures
        )
        return SituationPublic(
            run_id=self.run_id,
            hero_id=self.hero_id,
            adventure_run_id=self.adventure_run_id,
            scene_id=self.scene_id,
            campaign_title=self.campaign_title,
            adventure_title=self.adventure_title,
            scene_title=self.scene_title,
            truth=self.truth,
            consequences=self.consequences,
            pressure=self.pressure,
            hero=self.hero,
            actors=self.actors,
            fixtures=public_fixtures,
            loose_items=self.loose_items,
            exits=self.exits,
            recent=self.recent,
        )


def derive_role(
    *,
    is_hero: bool,
    state_hostile: bool | None,
    disposition: str | None,
    attacks: Sequence[AttackView],
) -> Role:
    """The one place a role is derived, never stored (← research, revised
    per verifier round 1): membership -> `hero`; an explicit
    `state["hostile"]` flag next, deciding outright (`True` -> `hostile`,
    `False` -> `ally` when armed, else `neutral`); otherwise a creature
    with no attacks at all is never a threat -> `neutral`; an armed
    stranger defaults to `hostile` -- goblins in the dark do not wait to
    be told they are dangerous -- unless its own authored `disposition`
    names friendliness (`_FRIENDLY_DISPOSITION_WORDS`), which reads as
    `ally` instead."""
    if is_hero:
        return "hero"
    if state_hostile is True:
        return "hostile"
    if state_hostile is False:
        return "ally" if attacks else "neutral"
    if not attacks:
        return "neutral"
    if disposition is not None:
        lowered = disposition.casefold()
        if any(word in lowered for word in _FRIENDLY_DISPOSITION_WORDS):
            return "ally"
    return "hostile"


@dataclass(frozen=True)
class RecalledTurn:
    """One semantic match plus the turn it belongs to (sprint 011/04, WI2)
    -- `events` holds the anchor narration together with every other
    `visibility='player'` event of the same `turn_id`, oldest first. An
    anchor whose own event never carried a `turn_id` yields `events`
    holding only that narration row."""

    turn_id: str | None
    anchor_event_id: str
    events: tuple[RecentEvent, ...]
