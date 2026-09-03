"""Is this bike legal for this licence, and does it fit this rider?

The two questions a shortlist has to survive, answered rule by rule with the
numbers in plain sight. Every rule reaches one of three verdicts — `pass`,
`fail`, `unknown` — and carries the arithmetic behind it as `evidence`, because a
verdict without its numbers is an opinion, and this project's whole claim is that
its answers come from verified specifications.

Three rules govern the output:

* **`unknown` is a first-class answer, and it always says why.** A specification
  the catalogue never verified makes the rule that needs it `unknown` with the
  gap named in the evidence — never a guessed value, never a silently dropped
  rule. The same goes for a rider figure the conversation has not stated: the
  advisor is meant to read "no inside leg was given" and ask.
* **The A2 limits are the ones the catalogue itself derives from.**
  `product_service.A2_MAX_POWER_KW` and `A2_MAX_POWER_TO_WEIGHT` are imported
  rather than restated, so this tool and the stored `a2_eligible` column can
  never drift apart (the 2.1 `_resolve_a2_eligible` derivation).
* **The rider-fit thresholds are heuristics, and they are labelled as such in the
  evidence.** Seat height against inside leg is a reach question with suspension
  sag in it; bike weight against experience is a confidence question. Where an
  inside leg is estimated from body height, the evidence says "estimated" and
  asks for the real figure.

`check` does one service read (the verified specifications of an approved model)
and then composes strings. Nothing is written, nothing is committed.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import catalogue_search_service, naming_service
from app.services.naming_service import NameLevel
from app.services.product_service import A2_MAX_POWER_KW, A2_MAX_POWER_TO_WEIGHT

# An A2 restriction may only be derived from a version making at most twice the
# restricted power (EU driving-licence directive) — the one licence rule that is
# not in the catalogue's own derivation, because it is about the *unrestricted*
# model.
A2_MAX_UNRESTRICTED_POWER_KW = A2_MAX_POWER_KW * 2

# How much taller than the rider's inside leg a seat may be before this check
# calls it a reach problem: a sagging suspension and thick soles buy a few
# centimetres, and below that a rider still gets both feet down at a stop.
SEAT_REACH_MARGIN_MM = 60

# Inside leg as a share of body height, for a rider who gave only their height.
# Disclosed in the evidence whenever it is used.
INSIDE_LEG_PER_HEIGHT = Decimal("0.47")

# The wet weight this check calls a lot of bike for a given experience level. A
# first bike that has to be pushed backwards up a driveway is the reason the rule
# exists; an experienced rider is not weight-limited here.
WEIGHT_LIMIT_KG = {"beginner": 200, "returning": 230}


class Licence(StrEnum):
    """The licence categories this check knows.

    A2 (35 kW, 0.20 kW/kg) and the unrestricted A. **A1 is deliberately out of
    scope:** its 125 cm³ / 11 kW class is not what this catalogue curates, and
    the verified `a2_eligible` column has no A1 counterpart to fall back on.
    """

    A2 = "A2"
    A = "A"


class RiderExperience(StrEnum):
    """How much riding the customer brings to the bike's weight."""

    BEGINNER = "beginner"
    RETURNING = "returning"
    EXPERIENCED = "experienced"


class Verdict(StrEnum):
    """The outcome of one rule. `unknown` is missing information, not a failure."""

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FitRule:
    """One checked rule: its stable id, its rendered label, the verdict, the numbers.

    `label` and `evidence` are server-composed English rendered verbatim by the
    chat UI (the same i18n exemption as operation messages); `rule` is the stable
    id the client keys on.
    """

    rule: str
    label: str
    verdict: Verdict
    evidence: str | None


@dataclass(frozen=True, slots=True)
class FitCheck:
    """The checked rules for one model, ready for the pinned tool result."""

    motorbike_id: str
    name: str
    rules: list[FitRule]


async def check(
    session: AsyncSession,
    motorbike_id: str,
    *,
    licence: Licence = Licence.A2,
    rider_height_cm: int | None = None,
    inside_leg_mm: int | None = None,
    experience: RiderExperience | None = None,
) -> FitCheck | None:
    """Check `motorbike_id` against a licence class and a rider's measurements.

    Args:
        session: Session the one read runs on; nothing is written or committed.
        motorbike_id: Catalogue id of an **approved** entry.
        licence: The licence the customer holds.
        rider_height_cm: Body height in centimetres, if stated.
        inside_leg_mm: Inside leg (inseam) in millimetres, if stated. Takes
            precedence over `rider_height_cm`, which only yields an estimate.
        experience: The rider's experience level, if stated.

    Returns:
        The rules, in reading order (licence first, then fit), or `None` when the
        id is not an approved catalogue entry — callers turn that into the pinned
        `{"unknownBike": …}` tool result.
    """
    specs = await catalogue_search_service.get_verified_specs(session, [motorbike_id])
    if not specs:
        return None

    entry = specs[0]
    rules = [
        *_licence_rules(licence, entry.values),
        _seat_height_rule(entry.values, rider_height_cm, inside_leg_mm),
        _weight_rule(entry.values, experience),
    ]
    # `YEAR_RANGE` is the pinned floor for a customer-visible single-bike answer
    # (docs/roadmap/model-naming-data-model.md §5): no context set here, since
    # this check is always about exactly one model.
    name = naming_service.render_name(entry.parts, min_level=NameLevel.YEAR_RANGE)
    return FitCheck(motorbike_id=entry.motorbike_id, name=name, rules=rules)


def _licence_rules(licence: Licence, values: dict[str, Any]) -> list[FitRule]:
    """Return the licence rules for `licence`.

    The unrestricted A licence has exactly one thing to say, and saying it is
    better than an empty licence section the customer has to interpret.
    """
    if licence is Licence.A:
        return [
            FitRule(
                rule="licence_unrestricted",
                label="Licence limits",
                verdict=Verdict.PASS,
                evidence="A full A licence has no power or power-to-weight limit.",
            )
        ]
    return _a2_rules(values)


def _a2_rules(values: dict[str, Any]) -> list[FitRule]:
    """Return the A2 rules: the power limit, the ratio, and the two conditional ones."""
    power_kw = values["power_kw"]
    wet_weight_kg = values["wet_weight_kg"]
    rules = [_a2_power_rule(power_kw), _a2_ratio_rule(power_kw, wet_weight_kg)]

    # Only worth a line when there is something to restrict: a model already
    # inside the limit needs no restricted version, and one whose power the
    # catalogue never verified cannot be assessed for one.
    if power_kw is not None and _decimal(power_kw) > A2_MAX_POWER_KW:
        rules.append(_a2_restricted_rule(power_kw, wet_weight_kg))

    # The catalogue's own eligibility flag is the fallback, not a third opinion:
    # it is derived from exactly the two numbers above (or set by an admin who
    # knew better), so it only adds information when the derivation above could
    # not be completed.
    if power_kw is None or wet_weight_kg is None:
        rules.append(_a2_catalogue_rule(values["a2_eligible"]))
    return rules


def _a2_power_rule(power_kw: Any) -> FitRule:
    """The A2 power ceiling: 35 kW, the boundary itself passing."""
    label = "A2 power limit"
    if power_kw is None:
        return FitRule(
            rule="a2_power",
            label=label,
            verdict=Verdict.UNKNOWN,
            evidence="The catalogue has no verified power output for this model.",
        )

    power = _decimal(power_kw)
    within = power <= A2_MAX_POWER_KW
    return FitRule(
        rule="a2_power",
        label=label,
        verdict=Verdict.PASS if within else Verdict.FAIL,
        evidence=(
            f"Verified power {_kw(power)} kW is "
            f"{'within' if within else 'above'} the A2 limit of {_plain(A2_MAX_POWER_KW)} kW."
        ),
    )


def _a2_ratio_rule(power_kw: Any, wet_weight_kg: Any) -> FitRule:
    """The A2 power-to-weight ceiling: 0.20 kW/kg, the boundary itself passing."""
    label = "A2 power-to-weight limit"
    missing = _missing_reason(power_kw, wet_weight_kg)
    if missing is not None:
        return FitRule(
            rule="a2_power_to_weight", label=label, verdict=Verdict.UNKNOWN, evidence=missing
        )

    power = _decimal(power_kw)
    weight = _decimal(wet_weight_kg)
    ratio = power / weight
    within = ratio <= A2_MAX_POWER_TO_WEIGHT
    return FitRule(
        rule="a2_power_to_weight",
        label=label,
        verdict=Verdict.PASS if within else Verdict.FAIL,
        evidence=(
            f"{_kw(power)} kW / {_plain(weight)} kg = {_ratio(ratio)} kW/kg, "
            f"{'within' if within else 'above'} the A2 limit of "
            f"{_limit(A2_MAX_POWER_TO_WEIGHT)} kW/kg."
        ),
    )


def _a2_restricted_rule(power_kw: Any, wet_weight_kg: Any) -> FitRule:
    """Whether a dealer-restricted 35 kW version of this model could be ridden on A2."""
    label = "A2 restricted version"
    power = _decimal(power_kw)
    if power > A2_MAX_UNRESTRICTED_POWER_KW:
        return FitRule(
            rule="a2_restricted_version",
            label=label,
            verdict=Verdict.FAIL,
            evidence=(
                f"An A2 restriction may only come from a version of at most "
                f"{_plain(A2_MAX_UNRESTRICTED_POWER_KW)} kW; this model makes {_kw(power)} kW."
            ),
        )

    if wet_weight_kg is None:
        return FitRule(
            rule="a2_restricted_version",
            label=label,
            verdict=Verdict.UNKNOWN,
            evidence=(
                f"A restriction to {_plain(A2_MAX_POWER_KW)} kW is permitted from "
                f"{_kw(power)} kW, but the catalogue has no verified wet weight, so the "
                "power-to-weight limit cannot be checked."
            ),
        )

    weight = _decimal(wet_weight_kg)
    ratio = A2_MAX_POWER_KW / weight
    within = ratio <= A2_MAX_POWER_TO_WEIGHT
    detail = (
        "Whether a restricted version is offered depends on the dealer."
        if within
        else f"That is still above the {_limit(A2_MAX_POWER_TO_WEIGHT)} kW/kg limit."
    )
    return FitRule(
        rule="a2_restricted_version",
        label=label,
        verdict=Verdict.PASS if within else Verdict.FAIL,
        evidence=(
            f"Restricted to {_plain(A2_MAX_POWER_KW)} kW: {_plain(A2_MAX_POWER_KW)} kW / "
            f"{_plain(weight)} kg = {_ratio(ratio)} kW/kg. {detail}"
        ),
    )


def _a2_catalogue_rule(a2_eligible: Any) -> FitRule:
    """The catalogue's verified A2 eligibility, used when the derivation is incomplete."""
    if a2_eligible is None:
        evidence = "The catalogue has no verified A2 eligibility for this model."
        verdict = Verdict.UNKNOWN
    else:
        evidence = (
            f"The catalogue records this model as "
            f"{'A2 eligible' if a2_eligible else 'not A2 eligible'}."
        )
        verdict = Verdict.PASS if a2_eligible else Verdict.FAIL
    return FitRule(
        rule="a2_eligible",
        label="A2 eligibility on record",
        verdict=verdict,
        evidence=evidence,
    )


def _seat_height_rule(
    values: dict[str, Any], rider_height_cm: int | None, inside_leg_mm: int | None
) -> FitRule:
    """Whether the rider can get their feet down: seat height against inside leg."""
    label = "Seat height fit"
    seat_height_mm = values["seat_height_mm"]
    if seat_height_mm is None:
        return FitRule(
            rule="seat_height_fit",
            label=label,
            verdict=Verdict.UNKNOWN,
            evidence="The catalogue has no verified seat height for this model.",
        )

    seat = int(seat_height_mm)
    if inside_leg_mm is not None:
        leg, basis = int(inside_leg_mm), f"a {int(inside_leg_mm)} mm inside leg"
    elif rider_height_cm is not None:
        leg = int(_decimal(rider_height_cm) * 10 * INSIDE_LEG_PER_HEIGHT)
        basis = f"an inside leg of about {leg} mm estimated for a {int(rider_height_cm)} cm rider"
    else:
        return FitRule(
            rule="seat_height_fit",
            label=label,
            verdict=Verdict.UNKNOWN,
            evidence=(
                f"The seat is {seat} mm, but no rider height or inside leg was given, "
                "so the reach cannot be judged."
            ),
        )

    reach = seat - leg
    within = reach <= SEAT_REACH_MARGIN_MM
    detail = (
        "both feet should reach the ground once the suspension sags"
        if within
        else "expect tiptoes only; a lower seat or a lowering kit would be needed"
    )
    estimate_note = (
        "" if inside_leg_mm is not None else " Give the actual inside leg to firm it up."
    )
    return FitRule(
        rule="seat_height_fit",
        label=label,
        verdict=Verdict.PASS if within else Verdict.FAIL,
        evidence=f"{seat} mm seat height against {basis} ({reach:+d} mm): {detail}.{estimate_note}",
    )


def _weight_rule(values: dict[str, Any], experience: RiderExperience | None) -> FitRule:
    """Whether the bike's wet weight suits the rider's experience."""
    label = "Weight for the rider's experience"
    wet_weight_kg = values["wet_weight_kg"]
    if wet_weight_kg is None:
        return FitRule(
            rule="weight_fit",
            label=label,
            verdict=Verdict.UNKNOWN,
            evidence="The catalogue has no verified wet weight for this model.",
        )

    weight = _plain(_decimal(wet_weight_kg))
    if experience is None:
        return FitRule(
            rule="weight_fit",
            label=label,
            verdict=Verdict.UNKNOWN,
            evidence=(
                f"The bike weighs {weight} kg wet, but the rider's experience level was not given."
            ),
        )

    limit = WEIGHT_LIMIT_KG.get(experience.value)
    if limit is None:
        return FitRule(
            rule="weight_fit",
            label=label,
            verdict=Verdict.PASS,
            evidence=f"{weight} kg wet is unremarkable for an experienced rider.",
        )

    within = _decimal(wet_weight_kg) <= limit
    audience = "a first bike" if experience is RiderExperience.BEGINNER else "a returning rider"
    return FitRule(
        rule="weight_fit",
        label=label,
        verdict=Verdict.PASS if within else Verdict.FAIL,
        evidence=(
            f"{weight} kg wet is {'within' if within else 'above'} the {limit} kg this "
            f"check suggests for {audience}."
        ),
    )


def _missing_reason(power_kw: Any, wet_weight_kg: Any) -> str | None:
    """Return why the ratio cannot be computed, or `None` when it can.

    A usable weight is part of "can be computed": a zero or negative wet weight
    would turn the ratio into arithmetic rather than information (the
    `_resolve_a2_eligible` guard, same reason).
    """
    if power_kw is None and wet_weight_kg is None:
        return "The catalogue has no verified power output or wet weight for this model."
    if power_kw is None:
        return (
            f"The wet weight of {_plain(_decimal(wet_weight_kg))} kg is verified, but the power "
            "output is not, so the ratio cannot be checked."
        )
    if wet_weight_kg is None:
        return (
            f"The power output of {_kw(_decimal(power_kw))} kW is verified, but the wet weight "
            "is not, so the ratio cannot be checked."
        )
    if _decimal(wet_weight_kg) <= 0:
        return "The verified wet weight is not a usable figure, so the ratio cannot be checked."
    return None


def _decimal(value: Any) -> Decimal:
    """Convert a specification value to `Decimal` without float noise.

    `get_verified_specs` unwraps `Numeric` columns to `float`, so the string round
    trip (the `product_service` precedent) is what keeps the comparisons exact —
    35.0 kW must not miss the 35 kW limit by a rounding artefact.
    """
    return Decimal(str(value))


def _kw(power: Decimal) -> str:
    """Render a measured power figure the way the catalogue stores it: one decimal."""
    return f"{power:.1f}"


def _plain(value: Decimal) -> str:
    """Render a weight or a whole-number limit without a pointless trailing zero.

    189.0 kg reads as "189 kg" and the A2 ceiling as "35 kW", which is how both
    are written outside a specification table.
    """
    return f"{value:.0f}" if value == value.to_integral_value() else f"{value:.1f}"


def _ratio(ratio: Decimal) -> str:
    """Render a power-to-weight ratio: three decimals, enough to see the margin."""
    return f"{ratio:.3f}"


def _limit(limit: Decimal) -> str:
    """Render the ratio limit as it is written in the licence rules: 0.20 kW/kg."""
    return f"{limit:.2f}"
