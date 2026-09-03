"""`licence_fit_check` — may this rider ride this bike, and does it fit them?

The two hard gates of a recommendation. "It's A2-legal" is a legal claim and
"you'll get your feet down" is a physical one, and both are the kind of statement
a language model will happily produce from memory. This tool takes them away from
memory: the verdicts come from `fit_check_service`, which reads the *verified*
specifications of an *approved* catalogue entry and applies the same A2 limits the
catalogue itself derives its `a2_eligible` column from.

What reaches the customer is a list of rules, each with a `pass`/`fail`/`unknown`
verdict and the numbers behind it in `evidence` — server-composed English the chat
UI renders verbatim. An `unknown` is a real answer here: a specification the
catalogue never verified, or a rider figure the conversation never stated, is
named as the gap it is instead of being filled in.
"""

from pydantic import ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from app.llm.agents.tools import (
    ToolContext,
    ToolModel,
    ToolSpec,
    UnknownBikeResult,
    resolve_references,
)
from app.services import fit_check_service
from app.services.fit_check_service import Licence, RiderExperience

NAME = "licence_fit_check"

# Plausible human ranges, so a unit slip (metres for centimetres, centimetres for
# millimetres) fails as an argument error instead of producing a confident verdict
# about a 1.7 cm rider.
MIN_RIDER_HEIGHT_CM = 120
MAX_RIDER_HEIGHT_CM = 230
MIN_INSIDE_LEG_MM = 500
MAX_INSIDE_LEG_MM = 1200

DESCRIPTION = (
    "Check one catalogue model against the customer's licence and body "
    "measurements. Identify the bike by catalogue id (motorbikeId) or by name "
    "(motorbikeName). Pass only what the conversation actually stated: riderHeightCm "
    "in centimetres, insideLegMm (inside leg / inseam) in millimetres, experience as "
    "beginner, returning or experienced. Returns one rule per check with a verdict of "
    "pass, fail or unknown and the numbers behind it — 'unknown' means the catalogue "
    "has not verified that specification or the customer has not given that figure, "
    "so ask instead of assuming. Licence A2 applies the 35 kW and 0.20 kW/kg limits; "
    "A is the unrestricted licence. If the bike is not in the catalogue the result is "
    '{"unknownBike": "<name>"} and nothing was checked.'
)


class LicenceFitCheckArgs(ToolModel):
    """Which bike, which licence, and whatever the customer said about themselves."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    motorbike_id: str | None = Field(
        default=None,
        description="Catalogue id of the model to check.",
    )
    motorbike_name: str | None = Field(
        default=None,
        description="Model name to check, as it was written in the conversation.",
    )
    licence: Licence = Field(
        default=Licence.A2,
        description="The licence the customer holds: A2 (restricted) or A (unrestricted).",
    )
    rider_height_cm: int | None = Field(
        default=None,
        ge=MIN_RIDER_HEIGHT_CM,
        le=MAX_RIDER_HEIGHT_CM,
        description="The customer's body height in centimetres, if stated.",
    )
    inside_leg_mm: int | None = Field(
        default=None,
        ge=MIN_INSIDE_LEG_MM,
        le=MAX_INSIDE_LEG_MM,
        description=(
            "The customer's inside leg (inseam) in millimetres, if stated. More reliable "
            "than body height for seat-height fit."
        ),
    )
    experience: RiderExperience | None = Field(
        default=None,
        description="The customer's riding experience, if stated.",
    )

    @model_validator(mode="after")
    def _check_a_bike_is_named(self) -> "LicenceFitCheckArgs":
        """Reject a call that does not say which bike to check."""
        if not (self.motorbike_id or self.motorbike_name):
            raise ValueError("Name the bike to check via motorbikeId or motorbikeName.")
        return self


class LicenceFitRule(ToolModel):
    """One checked rule: the stable id, the label, the verdict and its evidence.

    `label` and `evidence` are rendered verbatim by the chat UI; `verdict` is one
    of `pass`, `fail`, `unknown`.
    """

    rule: str
    label: str
    verdict: str
    evidence: str | None


class LicenceFitCheckResult(ToolModel):
    """The pinned result: which bike was checked, and every rule's verdict."""

    motorbike_id: str
    name: str
    rules: list[LicenceFitRule]


async def run(
    ctx: ToolContext, args: LicenceFitCheckArgs
) -> LicenceFitCheckResult | UnknownBikeResult:
    """Resolve the bike, run the rules and map them into the pinned shape.

    The service owns every verdict and every string; this function owns nothing
    but the resolution and the camelCase mapping.
    """
    reference = args.motorbike_id or args.motorbike_name or ""
    resolved = await resolve_references(
        ctx,
        motorbike_ids=[args.motorbike_id] if args.motorbike_id else (),
        names=[args.motorbike_name] if args.motorbike_name and not args.motorbike_id else (),
    )
    if resolved.unresolved is not None or not resolved.bikes:
        return UnknownBikeResult(unknown_bike=resolved.unresolved or reference)

    check = await fit_check_service.check(
        ctx.session,
        resolved.bikes[0].id,
        licence=args.licence,
        rider_height_cm=args.rider_height_cm,
        inside_leg_mm=args.inside_leg_mm,
        experience=args.experience,
    )
    if check is None:
        # The entry resolved a moment ago and has no verified specifications to
        # read now — nothing to check, so the honest answer is the same one an
        # unknown name gets.
        return UnknownBikeResult(unknown_bike=reference)

    return LicenceFitCheckResult(
        motorbike_id=check.motorbike_id,
        name=check.name,
        rules=[
            LicenceFitRule(
                rule=rule.rule,
                label=rule.label,
                verdict=rule.verdict.value,
                evidence=rule.evidence,
            )
            for rule in check.rules
        ],
    )


TOOL = ToolSpec(
    name=NAME,
    description=DESCRIPTION,
    args_schema=LicenceFitCheckArgs,
    run=run,
)
