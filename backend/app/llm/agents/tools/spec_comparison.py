"""`spec_comparison` — two to four models side by side, verified numbers only.

"How does the CB500F compare to the MT-07?" is the question a shortlist provokes,
and it is the one an advisor must not answer from memory. This tool builds the
table from the `verified` specification revisions of `approved` entries: every
frozen comparison column is a row, values are aligned to the bike order, and a
number the catalogue never verified is an explicit `null` — the UI renders it as
an em dash and the advisor is expected to name the gap rather than fill it.

Bikes are addressed by catalogue id or by name; a name the catalogue cannot
resolve makes the whole call answer with the shared `{"unknownBike": …}` result,
because a two-column table with a silently dropped bike answers a question nobody
asked.
"""

from typing import Any

from pydantic import ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from app.llm.agents.tools import (
    ResolvedBikes,
    ToolContext,
    ToolModel,
    ToolSpec,
    UnknownBikeResult,
    resolve_references,
)
from app.services import catalogue_search_service, naming_service
from app.services.catalogue_search_service import COMPARISON_SPEC_FIELDS
from app.services.naming_service import NameLevel

NAME = "spec_comparison"

# Fewer than two is not a comparison; more than four is a table nobody reads in a
# chat bubble (and the UI scrolls it horizontally at four already).
MIN_BIKES = 2
MAX_BIKES = 4

DESCRIPTION = (
    f"Compare the verified specifications of {MIN_BIKES} to {MAX_BIKES} catalogue "
    "models side by side. Identify each model by catalogue id (motorbikeIds) or "
    "by name (names) — mix both if that is what you have. Returns the bikes in "
    "the order given plus one row per specification field, with values aligned "
    "to that order. A value the catalogue has not verified is null: report it as "
    "unknown, never estimate it. If a name is not in the catalogue the result is "
    '{"unknownBike": "<name>"} and no comparison was made.'
)


class SpecComparisonArgs(ToolModel):
    """Which bikes to compare, by id or by name.

    Both lists are optional individually; together they must name between
    `MIN_BIKES` and `MAX_BIKES` bikes. Unknown keys are ignored, like every tool
    args schema: a stray key must not cost the call.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    motorbike_ids: list[str] = Field(
        default_factory=list,
        description="Catalogue ids of the models to compare.",
    )
    names: list[str] = Field(
        default_factory=list,
        description="Model names to compare, as they were written in the conversation.",
    )

    @model_validator(mode="after")
    def _check_reference_count(self) -> "SpecComparisonArgs":
        """Reject a call that cannot produce a comparison.

        Counted across both lists, because the model may address one bike by id
        and the other by name.
        """
        total = len(self.motorbike_ids) + len(self.names)
        if not MIN_BIKES <= total <= MAX_BIKES:
            raise ValueError(
                f"Name {MIN_BIKES} to {MAX_BIKES} bikes across motorbikeIds and names; got {total}."
            )
        return self


class ComparedBike(ToolModel):
    """One column header: which model this column is about."""

    motorbike_id: str
    name: str


class ComparisonRow(ToolModel):
    """One specification row: the field name and one value per bike.

    `field` is the frozen specification column in camelCase (`powerKw`,
    `seatHeightMm`, …) — the client maps it to a label and renders an unmapped one
    verbatim, so the vocabulary is the database's, not a translation's. `values`
    is positionally aligned to `bikes`; `null` means "not verified".
    """

    field: str
    values: list[Any]


class SpecComparisonResult(ToolModel):
    """The pinned comparison shape: the bike order, then every field as a row."""

    bikes: list[ComparedBike]
    rows: list[ComparisonRow]


async def run(
    ctx: ToolContext, args: SpecComparisonArgs
) -> SpecComparisonResult | UnknownBikeResult:
    """Resolve the references, load verified specs and transpose them into rows.

    Resolution first, because an unresolvable name ends the call. Then one service
    call for the values and the transposition — every `COMPARISON_SPEC_FIELDS`
    entry becomes a row whether or not any bike has the value, which is what makes
    a missing number visible instead of absent.
    """
    resolved: ResolvedBikes = await resolve_references(
        ctx, motorbike_ids=args.motorbike_ids, names=args.names
    )
    if resolved.unresolved is not None:
        return UnknownBikeResult(unknown_bike=resolved.unresolved)

    specs = await catalogue_search_service.get_verified_specs(
        ctx.session, [motorbike.id for motorbike in resolved.bikes]
    )
    # The compared bikes are each other's context, floored at the year range
    # (D5's binding per-caller table): a comparison is exactly the situation two
    # same-named generations must be told apart in.
    names = naming_service.render_names(
        [entry.parts for entry in specs], min_level=NameLevel.YEAR_RANGE
    )
    return SpecComparisonResult(
        bikes=[
            ComparedBike(motorbike_id=entry.motorbike_id, name=names[entry.motorbike_id])
            for entry in specs
        ],
        rows=[
            ComparisonRow(
                field=to_camel(field),
                values=[entry.values[field] for entry in specs],
            )
            for field in COMPARISON_SPEC_FIELDS
        ],
    )


TOOL = ToolSpec(
    name=NAME,
    description=DESCRIPTION,
    args_schema=SpecComparisonArgs,
    run=run,
)
