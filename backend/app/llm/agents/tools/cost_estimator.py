"""`cost_estimator` — what one catalogue model costs to buy and to run, honestly.

The running cost is what turns a shortlist into a decision, and it is also where a
confident-sounding invention does the most damage. So this tool never invents: the
numbers come from `cost_estimator_service`, which starts from the *verified* price
of an *approved* model, applies the versioned coefficient table in
`app/services/cost_data.py`, and writes every choice it made into `assumptions`.

Three properties the result carries on purpose:

* **It labels itself an estimate.** `assumptions` is never empty and its last line
  says "not a quote"; `coefficientsVersion` says which table produced the numbers,
  so an estimate a customer saw months ago stays explainable. The chat UI shows an
  "Estimate" chip on top of that.
* **It is reproducible.** No clock, no randomness, no pricing API — the same bike
  and the same mileage always give the same euros.
* **A missing verified input costs a line, not the estimate.** A model whose price
  the catalogue never verified simply has no purchase-price line, and the
  assumptions say so.
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
from app.services import cost_estimator_service
from app.services.cost_data import DEFAULT_ANNUAL_KM

NAME = "cost_estimator"

# A plausible mileage range: zero is a bike that sits in a garage, and above this
# nobody is estimating a leisure motorcycle any more. A slip outside it is an
# argument error rather than a €40,000 fuel line.
MIN_ANNUAL_KM = 0
MAX_ANNUAL_KM = 60000

DESCRIPTION = (
    "Estimate what one catalogue model costs to buy and to run for a year. "
    "Identify the bike by catalogue id (motorbikeId) or by name (motorbikeName), and "
    f"pass annualKm when the customer said how much they ride (default {DEFAULT_ANNUAL_KM:,} "
    "km/year). Returns line items in EUR, their total, the assumptions the numbers rest "
    "on and the version of the coefficient table used. These are heuristics for Germany, "
    "not quotes: present them as an estimate and repeat the assumptions that matter. A "
    "cost the catalogue has no verified specification for is left out and named in the "
    'assumptions. If the bike is not in the catalogue the result is {"unknownBike": '
    '"<name>"} and nothing was estimated.'
)


class CostEstimatorArgs(ToolModel):
    """Which bike to cost, and how much the customer rides."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    motorbike_id: str | None = Field(
        default=None,
        description="Catalogue id of the model to cost.",
    )
    motorbike_name: str | None = Field(
        default=None,
        description="Model name to cost, as it was written in the conversation.",
    )
    annual_km: int = Field(
        default=DEFAULT_ANNUAL_KM,
        ge=MIN_ANNUAL_KM,
        le=MAX_ANNUAL_KM,
        description="Kilometres the customer rides per year; fuel and maintenance scale with it.",
    )

    @model_validator(mode="after")
    def _check_a_bike_is_named(self) -> "CostEstimatorArgs":
        """Reject a call that does not say which bike to cost."""
        if not (self.motorbike_id or self.motorbike_name):
            raise ValueError("Name the bike to cost via motorbikeId or motorbikeName.")
        return self


class CostLineItem(ToolModel):
    """One line of the estimate: a verbatim label and whole euros.

    The label carries the period ("/year", "(one-off)") because that is the only
    thing telling the customer what the number means.
    """

    label: str
    amount: int


class CostEstimatorResult(ToolModel):
    """The pinned estimate shape: lines, total, assumptions, coefficient version."""

    motorbike_id: str
    name: str
    currency: str
    line_items: list[CostLineItem]
    total: int
    assumptions: list[str]
    coefficients_version: str


async def run(ctx: ToolContext, args: CostEstimatorArgs) -> CostEstimatorResult | UnknownBikeResult:
    """Resolve the bike, cost it and map the estimate into the pinned shape."""
    reference = args.motorbike_id or args.motorbike_name or ""
    resolved = await resolve_references(
        ctx,
        motorbike_ids=[args.motorbike_id] if args.motorbike_id else (),
        names=[args.motorbike_name] if args.motorbike_name and not args.motorbike_id else (),
    )
    if resolved.unresolved is not None or not resolved.bikes:
        return UnknownBikeResult(unknown_bike=resolved.unresolved or reference)

    estimate = await cost_estimator_service.estimate(
        ctx.session, resolved.bikes[0].id, annual_km=args.annual_km
    )
    if estimate is None:
        # Resolved a moment ago, unreadable now: the same honest answer an unknown
        # name gets, rather than an estimate of nothing.
        return UnknownBikeResult(unknown_bike=reference)

    return CostEstimatorResult(
        motorbike_id=estimate.motorbike_id,
        name=estimate.name,
        currency=estimate.currency,
        line_items=[
            CostLineItem(label=line.label, amount=line.amount) for line in estimate.line_items
        ],
        total=estimate.total,
        assumptions=estimate.assumptions,
        coefficients_version=estimate.coefficients_version,
    )


TOOL = ToolSpec(
    name=NAME,
    description=DESCRIPTION,
    args_schema=CostEstimatorArgs,
    run=run,
)
