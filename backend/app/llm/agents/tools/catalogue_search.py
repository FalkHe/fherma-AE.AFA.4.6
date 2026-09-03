"""`catalogue_search` — which approved models satisfy the stated constraints.

The structured half of advanced retrieval, as a tool: the advisor states the
bounds the conversation supports (licence, budget, seat height, category) and the
database answers which curated models meet them. This is the tool that keeps a
recommendation honest — "fits an A2 licence" is decided by a `WHERE` clause over
verified specifications, never by the language model's memory.

It adds nothing to step 3.8: the args schema *is* the frozen `SpecFilters`
surface (camel-aliased for the model), and the search is
`catalogue_search_service.find_motorbike_ids`. The only decisions here are
presentational — which columns a result line carries, and the cap.
"""

from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

from app.llm.agents.tools import ToolContext, ToolModel, ToolSpec
from app.llm.query_translation import SpecFilters
from app.services import catalogue_search_service, naming_service
from app.services.naming_service import NameLevel

NAME = "catalogue_search"

# How many models one call returns. `totalCount` still reports every match, so
# the advisor can say "23 models fit, here are the closest twelve" instead of
# pretending the shortlist is complete. The UI shows eight of them plus "+n more".
MAX_RESULTS = 12

DESCRIPTION = (
    "Search the curated motorcycle catalogue by verified specifications. "
    "State only the constraints the conversation actually supports — every "
    "filter is a claim about the customer, and an invented one hides suitable "
    "models. Units are fixed: kW for power, kg for wet weight, mm for seat "
    "height, cm³ for displacement. Returns up to "
    f"{MAX_RESULTS} matching models with a few key specifications each, plus "
    "totalCount (how many models matched in total). A specification the "
    "catalogue has not verified comes back as null — say so, never guess it."
)


class CatalogueSearchArgs(SpecFilters):
    """The frozen filter surface, camel-aliased for the model.

    A subclass rather than a restatement: step 3.8 pinned `SpecFilters` as the one
    definition of what can be filtered, and a second copy of nine bounds would
    drift. Subclassing also means an instance *is* a `SpecFilters`, so the search
    service takes it unchanged.

    Inherited from `SpecFilters` on purpose: unknown keys are ignored (an invented
    filter must not fail the call) and the JSON schema names every property in
    `required` with `null` unions for the optional ones (the 2.17 provider
    finding) — the model answers `null` for what the conversation did not state.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")


class CatalogueSearchHit(ToolModel):
    """One matching model, with the specifications a shortlist line shows.

    Every specification is nullable: the catalogue shows a verified number or
    nothing at all.
    """

    motorbike_id: str
    name: str
    category: str | None
    power_kw: float | None
    wet_weight_kg: float | None
    seat_height_mm: int | None
    price_band: str | None


class CatalogueSearchResult(ToolModel):
    """The pinned result: the capped shortlist plus the true match count."""

    results: list[CatalogueSearchHit]
    total_count: int


async def run(ctx: ToolContext, args: CatalogueSearchArgs) -> CatalogueSearchResult:
    """Search the catalogue and render the capped shortlist.

    Two service calls: the shortlist (ids, name-ordered) and the display values
    for the ids that survive the cap. `totalCount` is the full match count, so
    capping never looks like a narrower catalogue.
    """
    motorbike_ids = await catalogue_search_service.find_motorbike_ids(ctx.session, args)
    specs = await catalogue_search_service.get_verified_specs(
        ctx.session, motorbike_ids[:MAX_RESULTS]
    )
    # The returned rows are each other's context (D5): a name escalates to its
    # year range only when two of *these* results would otherwise render alike.
    names = naming_service.render_names([entry.parts for entry in specs], min_level=NameLevel.MODEL)
    return CatalogueSearchResult(
        results=[
            CatalogueSearchHit(
                motorbike_id=entry.motorbike_id,
                name=names[entry.motorbike_id],
                category=entry.values["category"],
                power_kw=entry.values["power_kw"],
                wet_weight_kg=entry.values["wet_weight_kg"],
                seat_height_mm=entry.values["seat_height_mm"],
                price_band=entry.values["price_band"],
            )
            for entry in specs
        ],
        total_count=len(motorbike_ids),
    )


TOOL = ToolSpec(
    name=NAME,
    description=DESCRIPTION,
    args_schema=CatalogueSearchArgs,
    run=run,
)
