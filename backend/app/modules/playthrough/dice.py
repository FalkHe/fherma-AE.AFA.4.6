"""Dice the server rolls itself, and the formula a roll derives from --
never a number a caller passed (brief WI1, ← D6).

Two independent halves, both engine-free -- no database, no session:

- `roll(expression)` parses `NdM+-K`, rolls behind the `_rng()` seam
  (returns a `random.Random`, so a test can replace it with a
  deterministic one) and caps an expression at 20 dice of at most 100
  faces, so a hostile or mistaken expression can never ask for a huge
  pool.
- `derive_formula(kind, actor, context, *, campaign_id, version)` works
  out *what* to roll from the kind of roll and who is rolling: an
  ability score off the actor -- its own `state` for a character
  (`template_id is None`), otherwise its template's stat block, read
  through `content.service` only (never the database) -- or an attack's
  `to_hit`/`damage` off an item template (`context["item_id"]`) or, when
  none is given, the actor's own stat block, disambiguated by the
  attack's own name (`context["attack"]`), never by position, since a
  monster may carry more than one attack and is not an item itself (the
  product owner's mid-sprint ruling).

Neither function takes `formula`, `modifier`, `bonus`, `faces` or
`total` -- there is no parameter through which a caller could pass one
of those in. The only caller-supplied number is a `custom` roll's own
`context["expression"]`, reachable under no other kind.
"""

from __future__ import annotations

import random
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.core.errors import ErrorCode
from app.modules.content import service as content_service
from app.modules.content.schemas import Abilities, Attack, CreatureTemplate, ItemTemplate
from app.modules.playthrough.models import GameObject
from app.modules.playthrough.schemas import RollKind

MAX_DICE = 20
MAX_FACES = 100

_EXPRESSION_RE = re.compile(r"^(?P<count>\d+)d(?P<sides>\d+)(?P<modifier>[+-]\d+)?$")


class InvalidDiceExpressionError(Exception):
    """`roll` was asked to roll something other than `NdM+-K`, or an `N`/`M`
    outside the cap -- names the offending expression (`.expression`) so a
    caller, including `app playthrough roll`, can show it back verbatim.
    """

    code = ErrorCode.VALIDATION_ERROR

    def __init__(self, expression: str) -> None:
        self.expression = expression
        super().__init__(f"invalid dice expression: {expression!r}")


@dataclass(frozen=True)
class DiceRoll:
    faces: list[int]
    modifier: int
    total: int


def _rng() -> random.Random:
    """The one seam `roll` draws entropy from. Tests replace this function,
    never `random` itself, so a suite can pin the sequence of faces
    without reaching into the stdlib module every other caller also
    uses."""
    return random.Random()


def roll(expression: str) -> DiceRoll:
    """Parses `NdM+-K` and rolls it through `_rng()`. Anything that does not
    match, or an `N`/`M` outside `1..MAX_DICE` / `1..MAX_FACES`, raises
    `InvalidDiceExpressionError` naming `expression` -- the same check
    covers both a malformed string and a well-formed one asking for too
    much."""
    match = _EXPRESSION_RE.match(expression.strip()) if isinstance(expression, str) else None
    if match is None:
        raise InvalidDiceExpressionError(expression)

    count = int(match["count"])
    sides = int(match["sides"])
    modifier = int(match["modifier"]) if match["modifier"] else 0

    if not (1 <= count <= MAX_DICE) or not (1 <= sides <= MAX_FACES):
        raise InvalidDiceExpressionError(expression)

    rng = _rng()
    faces = [rng.randint(1, sides) for _ in range(count)]
    return DiceRoll(faces=faces, modifier=modifier, total=sum(faces) + modifier)


def _ability_modifier(score: int) -> int:
    """The SRD's own formula -- floor division, so a score of 7 gives -2,
    not -1 (the product owner's standing instruction: SRD rules win
    wherever something is ambiguous)."""
    return (score - 10) // 2


def _signed_d20(modifier: int) -> str:
    return "1d20" if modifier == 0 else f"1d20{modifier:+d}"


def _actor_abilities(actor: GameObject, *, campaign_id: str, version: str) -> Abilities:
    """A character (`template_id is None`) keeps its six scores in its own
    `state["abilities"]`; a template-born creature has none of its own --
    they live on its template's stat block, read read-only through
    `content.service` (never a database call)."""
    if actor.template_id is None:
        return Abilities.model_validate(actor.state["abilities"])
    template = content_service.load_object_template(campaign_id, version, actor.template_id)
    if not isinstance(template, CreatureTemplate):
        raise ValueError(f"object template has no abilities: {actor.template_id}")
    return template.stat_block.abilities


def _select_attack(attacks: list[Attack], name: str | None) -> Attack:
    """Picks one attack out of a list by its own name -- never by position,
    since a monster may carry more than one (brief WI1). With only one
    attack available, the name may be omitted."""
    if name is not None:
        for attack in attacks:
            if attack.name == name:
                return attack
        raise ValueError(f"no attack named {name!r}")
    if len(attacks) == 1:
        return attacks[0]
    raise ValueError("more than one attack is available; context['attack'] must name one")


def _attacks_for(
    actor: GameObject, *, item_id: str | None, campaign_id: str, version: str
) -> list[Attack]:
    """An item template's attacks when `item_id` is given; otherwise the
    actor's own stat block -- a monster's attack is not an item (brief
    WI1)."""
    if item_id is not None:
        template = content_service.load_object_template(campaign_id, version, item_id)
        if not isinstance(template, ItemTemplate):
            raise ValueError(f"object template is not an item: {item_id}")
        return template.attacks
    if actor.template_id is None:
        raise ValueError("a character's attack must name context['item_id']")
    template = content_service.load_object_template(campaign_id, version, actor.template_id)
    if not isinstance(template, CreatureTemplate):
        raise ValueError(f"object template has no attacks: {actor.template_id}")
    return template.stat_block.attacks


def derive_formula(
    kind: RollKind,
    actor: GameObject,
    context: Mapping[str, Any],
    *,
    campaign_id: str,
    version: str,
) -> str:
    """The server's own derivation, `kind` by `kind` (AC1, ← D6):

    - `attack` / `damage` -- the chosen attack's `to_hit` / `damage`, from
      `context["item_id"]`'s template when given, otherwise the actor's
      own stat block; `context["attack"]` names which one when there is
      more than one to choose from.
    - `ability_check` / `saving_throw` -- the modifier of the ability
      named in `context["ability"]`.
    - `initiative` -- the actor's own Dexterity modifier.
    - `custom` -- `context["expression"]`, verbatim, reachable only under
      this one kind and mixed with nothing derived.

    Takes no `formula`, `modifier`, `bonus`, `faces` or `total` parameter
    -- there is no way to pass one in.
    """
    if kind == "custom":
        return context["expression"]

    if kind in ("attack", "damage"):
        attacks = _attacks_for(
            actor, item_id=context.get("item_id"), campaign_id=campaign_id, version=version
        )
        attack = _select_attack(attacks, context.get("attack"))
        return _signed_d20(attack.to_hit) if kind == "attack" else attack.damage

    if kind in ("ability_check", "saving_throw"):
        abilities = _actor_abilities(actor, campaign_id=campaign_id, version=version)
        score = getattr(abilities, context["ability"])
        return _signed_d20(_ability_modifier(score))

    if kind == "initiative":
        abilities = _actor_abilities(actor, campaign_id=campaign_id, version=version)
        return _signed_d20(_ability_modifier(abilities.dexterity))

    raise ValueError(f"unknown roll kind: {kind}")
