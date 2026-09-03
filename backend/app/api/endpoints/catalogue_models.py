"""The `catalogue-models` resource: the customer's read-only view of the catalogue.

The whole router carries `current_user` — **not** `current_admin`: this is the
customer surface (admins are users too), and `/api/products` stays admin-only, so
no unreviewed number and no curation state can ever leak through here. There is
no write route and therefore no `csrf_protect`.

Two routes, both showing **approved models only, for every role**:

* the list — one browse page, slim cards, filtered and sorted server-side. It
  costs exactly three round trips regardless of page size: one
  `browse_motorbikes` (page + count), one `manufacturer_service.get_by_ids` and
  one `product_service.newest_approved_images`;
* the detail — everything the model page renders in one document (verified
  specification, the Wikipedia prose, the provenance list, the approved
  pictures), because a customer page that fans out into four requests is four
  chances to render half a bike.

No SQL lives here: the filter vocabulary is `SpecFilters` (the one definition,
shared with the advisor's query translation) and the statements are
`catalogue_search_service`'s. What this module does own is the **wire**: turning
`filter[…]` query parameters into that filter object, an unknown vocabulary
member into a 400 `invalid-filter`, and anything that is not an approved model
into a 404 `not-found` — unknown, backlog, in review and rejected ids are
deliberately indistinguishable, so the endpoint cannot be used to discover what
the catalogue is working on.
"""

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import jsonapi
from app.api.deps import current_user
from app.api.schemas.catalogue_models import (
    CatalogueImage,
    CatalogueModelAttributes,
    CatalogueModelDocument,
    CatalogueModelListDocument,
    CatalogueModelResource,
    CatalogueModelSpecs,
    CatalogueModelSummaryAttributes,
    CatalogueModelSummaryResource,
    CatalogueSource,
)
from app.api.schemas.images import variant_urls
from app.api.schemas.products import PriceBand, ProductVariant, SpecCategory
from app.db.models.manufacturer import Manufacturer
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.db.models.motorbike_image import ImageStatus, MotorbikeImage
from app.db.models.source_document import SourceDocument, SourceType
from app.db.session import get_db_session
from app.llm.extraction import _QUANTITIES
from app.llm.query_translation import SpecFilters
from app.services import (
    catalogue_search_service,
    document_service,
    manufacturer_service,
    naming_service,
    product_service,
)
from app.services.catalogue_search_service import (
    COMPARISON_SPEC_FIELDS,
    BrowseRow,
    BrowseSort,
)
from app.services.naming_service import NameLevel

router = APIRouter(
    prefix="/catalogue-models",
    tags=["catalogue-models"],
    dependencies=[Depends(current_user)],
)

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
MotorbikeIdDep = Annotated[str, Path(description="ULID of the catalogue model.")]

CATEGORY_FILTER_DESCRIPTION = "Comma-separated list of categories: " + ", ".join(
    member.value for member in SpecCategory
)
PRICE_BAND_FILTER_DESCRIPTION = "Comma-separated list of price bands: " + ", ".join(
    member.value for member in PriceBand
)
MANUFACTURER_FILTER_DESCRIPTION = (
    "Comma-separated list of manufacturer ULIDs; an unknown id matches nothing."
)


def _parse_vocabulary_filter(
    raw: str | None, vocabulary: type[StrEnum], description: str
) -> list[str]:
    """Turn one comma-separated `filter[…]` value into pinned vocabulary members.

    An empty list means "not filtered" — `SpecFilters` spells both list bounds
    that way. An unknown member is a 400 `invalid-filter` rather than a silently
    empty page: a customer whose filter is mistyped must not be told the
    catalogue holds nothing.
    """
    members = jsonapi.parse_filter(raw)
    if members is None:
        return []

    try:
        return [vocabulary(member).value for member in members]
    except ValueError as error:
        raise jsonapi.JsonApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid-filter",
            detail=f"{description}.",
        ) from error


def _manufacturer_name(
    manufacturer_id: str | None, manufacturers: Mapping[str, Manufacturer]
) -> str | None:
    """Return the display name behind a brand id, or `None` when there is none."""
    if manufacturer_id is None:
        return None
    manufacturer = manufacturers.get(manufacturer_id)
    return None if manufacturer is None else manufacturer.name


def _image_url(motorbike_id: str, images: Mapping[str, MotorbikeImage]) -> str | None:
    """Return the card-variant URL of a model's newest approved image, if any.

    A model without an approved picture is absent from the mapping (the 4.3
    contract) and gets `null` — the grid renders a placeholder, never a pending
    picture.
    """
    image = images.get(motorbike_id)
    return None if image is None else variant_urls(motorbike_id, image.id).card


def _summary_resource(
    row: BrowseRow,
    name: str,
    manufacturers: Mapping[str, Manufacturer],
    images: Mapping[str, MotorbikeImage],
) -> CatalogueModelSummaryResource:
    """Project one browse row onto a card resource object.

    The summary values are read by name rather than splatted, so a change to
    `SUMMARY_SPEC_FIELDS` fails here instead of quietly dropping a card line.
    `name` is rendered by the caller against the whole page as context (D5's
    binding table) — `row.name` alone would be the no-context convenience, which
    is not what a browse page needs.
    """
    values = row.values
    return CatalogueModelSummaryResource(
        id=row.motorbike_id,
        attributes=CatalogueModelSummaryAttributes(
            name=name,
            manufacturer=_manufacturer_name(row.manufacturer_id, manufacturers),
            category=values["category"],
            engine_cc=values["engine_cc"],
            power_kw=values["power_kw"],
            wet_weight_kg=values["wet_weight_kg"],
            seat_height_mm=values["seat_height_mm"],
            a2_eligible=values["a2_eligible"],
            price_band=values["price_band"],
            msrp_eur=values["msrp_eur"],
            image_url=_image_url(row.motorbike_id, images),
        ),
    )


def _specs(values: Mapping[str, Any] | None) -> CatalogueModelSpecs:
    """Project the verified specification values, or an all-`null` specification.

    An approved model without a verified revision still renders a full table of
    gaps — the same honesty rule `get_verified_specs` applies per value. Every
    field is required on the model, so a missing key is a loud failure here
    rather than a silently absent line on the detail page.
    """
    return CatalogueModelSpecs.model_validate(
        dict.fromkeys(COMPARISON_SPEC_FIELDS) if values is None else values
    )


def _article(documents: Sequence[SourceDocument]) -> str | None:
    """Return the Wikipedia document's markdown, or `None` when there is none.

    Wikipedia only, on purpose (D4): scraped product and magazine pages are
    marketing prose, and serving them wholesale is exactly what this project
    exists not to do. They appear in `sources` as a link instead.
    """
    return next(
        (
            document.content_markdown
            for document in documents
            if document.source_type is SourceType.WIKIPEDIA
        ),
        None,
    )


def _sources(documents: Sequence[SourceDocument]) -> list[CatalogueSource]:
    """Project the provenance list, in the service's order (Wikipedia first)."""
    return [
        CatalogueSource(source_title=document.source_title, source_url=document.source_url)
        for document in documents
    ]


def _variants(motorbike: Motorbike) -> list[ProductVariant]:
    """Project the row's stored trims (D1/D2, §2.5), detail only (D6).

    `motorbike.variants` can be `None` in the in-memory test double (a
    server-default gap that never happens in real Postgres, per 6.15's landed
    note) — guarded the same way `products.py`'s equivalent helper is.
    """
    return [ProductVariant.model_validate(variant) for variant in motorbike.variants or []]


def _image(image: MotorbikeImage) -> CatalogueImage:
    """Project one picture: the deterministic variant URLs plus its attribution."""
    variants = variant_urls(image.motorbike_id, image.id)
    return CatalogueImage(
        thumb=variants.thumb,
        card=variants.card,
        detail=variants.detail,
        attribution=image.attribution,
    )


def _images(images: Sequence[MotorbikeImage]) -> list[CatalogueImage]:
    """Project the approved pictures, in the service's order (newest first)."""
    return [_image(image) for image in images]


async def _approved_or_404(session: AsyncSession, motorbike_id: str) -> Motorbike:
    """Load an approved catalogue entry or fail with the pinned 404 error document.

    Unknown and not-approved are the same answer by design: an id that is in the
    backlog, in review or rejected must not be distinguishable from one that was
    never in the catalogue.
    """
    motorbike = await product_service.get_motorbike(session, motorbike_id)
    if motorbike is None or motorbike.status is not MotorbikeStatus.APPROVED:
        raise jsonapi.JsonApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not-found",
            detail=f"No catalogue model with id '{motorbike_id}'.",
        )
    return motorbike


@router.get(
    "",
    response_model=CatalogueModelListDocument,
    summary="Browse the catalogue",
    responses=jsonapi.error_responses(status.HTTP_400_BAD_REQUEST),
)
async def list_catalogue_models(
    session: SessionDep,
    page: jsonapi.PaginationDep,
    category: Annotated[
        str | None,
        Query(alias="filter[category]", description=CATEGORY_FILTER_DESCRIPTION),
    ] = None,
    price_band: Annotated[
        str | None,
        Query(alias="filter[priceBand]", description=PRICE_BAND_FILTER_DESCRIPTION),
    ] = None,
    manufacturer: Annotated[
        str | None,
        Query(alias="filter[manufacturer]", description=MANUFACTURER_FILTER_DESCRIPTION),
    ] = None,
    # `ge`/`le` mirror `SpecFilters`' own plausibility windows (`_QUANTITIES`
    # in `app.llm.extraction`), imported rather than restated: `SpecFilters`
    # itself silently drops an out-of-range bound (the landed 4.4 caveat)
    # instead of rejecting it, so this is what makes an absurd filter value a
    # 422 at the wire instead of a silently widened result.
    engine_cc_min: Annotated[
        int | None,
        Query(
            alias="filter[engineCcMin]",
            description="Smallest displacement in cm³.",
            ge=_QUANTITIES["engine_cc"].minimum,
            le=_QUANTITIES["engine_cc"].maximum,
        ),
    ] = None,
    engine_cc_max: Annotated[
        int | None,
        Query(
            alias="filter[engineCcMax]",
            description="Largest displacement in cm³.",
            ge=_QUANTITIES["engine_cc"].minimum,
            le=_QUANTITIES["engine_cc"].maximum,
        ),
    ] = None,
    power_kw_min: Annotated[
        float | None,
        Query(
            alias="filter[powerKwMin]",
            description="Smallest maximum power in kW.",
            ge=_QUANTITIES["power_kw"].minimum,
            le=_QUANTITIES["power_kw"].maximum,
        ),
    ] = None,
    power_kw_max: Annotated[
        float | None,
        Query(
            alias="filter[powerKwMax]",
            description="Largest maximum power in kW.",
            ge=_QUANTITIES["power_kw"].minimum,
            le=_QUANTITIES["power_kw"].maximum,
        ),
    ] = None,
    wet_weight_kg_max: Annotated[
        float | None,
        Query(
            alias="filter[wetWeightKgMax]",
            description="Heaviest wet weight in kg.",
            ge=_QUANTITIES["wet_weight_kg"].minimum,
            le=_QUANTITIES["wet_weight_kg"].maximum,
        ),
    ] = None,
    seat_height_mm_max: Annotated[
        int | None,
        Query(
            alias="filter[seatHeightMmMax]",
            description="Highest seat height in mm.",
            ge=_QUANTITIES["seat_height_mm"].minimum,
            le=_QUANTITIES["seat_height_mm"].maximum,
        ),
    ] = None,
    a2_eligible: Annotated[
        bool | None,
        Query(alias="filter[a2Eligible]", description="Restrict to A2-eligible models."),
    ] = None,
    sort: Annotated[
        BrowseSort,
        Query(description="Ordering; price sorts put models without a price last."),
    ] = BrowseSort.NAME,
) -> CatalogueModelListDocument:
    """Return one page of approved models, filtered and sorted.

    Comma-separated members of one filter are OR-ed, different filters are
    AND-ed. A stated specification bound drops models whose verified value is
    unknown (a missing number cannot support a claim), while unfiltered browsing
    keeps them — the pinned NULL-spec browse rule.
    """
    filters = SpecFilters(
        categories=_parse_vocabulary_filter(category, SpecCategory, CATEGORY_FILTER_DESCRIPTION),
        price_bands=_parse_vocabulary_filter(price_band, PriceBand, PRICE_BAND_FILTER_DESCRIPTION),
        engine_cc_min=engine_cc_min,
        engine_cc_max=engine_cc_max,
        power_kw_min=power_kw_min,
        power_kw_max=power_kw_max,
        wet_weight_kg_max=wet_weight_kg_max,
        seat_height_mm_max=seat_height_mm_max,
        a2_eligible=a2_eligible,
    )

    rows, total = await catalogue_search_service.browse_motorbikes(
        session,
        filters=filters,
        manufacturer_ids=jsonapi.parse_filter(manufacturer),
        sort=sort,
        limit=page.limit,
        offset=page.offset,
    )
    # Two set-based reads for the whole page, never one per card.
    manufacturers = await manufacturer_service.get_by_ids(
        session, [row.manufacturer_id for row in rows if row.manufacturer_id is not None]
    )
    images = await product_service.newest_approved_images(
        session, [row.motorbike_id for row in rows]
    )
    # The page is its own context (D5's binding table): a name escalates to its
    # year range only when two rows *on this page* would otherwise render alike.
    names = naming_service.render_names([row.parts for row in rows], min_level=NameLevel.MODEL)

    return CatalogueModelListDocument(
        data=[
            _summary_resource(row, names[row.motorbike_id], manufacturers, images) for row in rows
        ],
        meta=jsonapi.Meta(total_count=total),
    )


@router.get(
    "/{motorbike_id}",
    response_model=CatalogueModelDocument,
    summary="Read a catalogue model",
    responses=jsonapi.error_responses(status.HTTP_404_NOT_FOUND),
)
async def get_catalogue_model(
    session: SessionDep, motorbike_id: MotorbikeIdDep
) -> CatalogueModelDocument:
    """Return one approved model with its specification, prose, sources and images."""
    motorbike = await _approved_or_404(session, motorbike_id)

    specs = await catalogue_search_service.get_verified_specs(session, [motorbike.id])
    manufacturers = await manufacturer_service.get_by_ids(
        session, [] if motorbike.manufacturer_id is None else [motorbike.manufacturer_id]
    )
    # `listing` documents are excluded (D12, fourth carve-out): a classifieds
    # link is not provenance for a specification — it never reaches this
    # customer-facing `sources[]` projection, even though `_article` below
    # would ignore it anyway. Admin surfaces (documents.py, products.py) keep
    # showing `listing` documents on purpose — that is where an admin audits
    # what the price research fetched.
    documents = await document_service.list_for_motorbike(
        session, motorbike.id, exclude_source_types=(SourceType.LISTING,)
    )
    # Approved pictures only, stated explicitly: `list_images` is unfiltered by
    # default, so the customer gallery must never rely on the default.
    images = await product_service.list_images(
        session, motorbike_id=motorbike.id, statuses=[ImageStatus.APPROVED]
    )

    # An approved model always has exactly one `VerifiedSpecs` entry (the outer
    # join keeps a row even with no verified revision), so its `parts` is
    # already loaded — no second query for the name in the normal case. `()`
    # context, `YEAR_RANGE` floor: the pinned detail-page level (D5's binding
    # table). The `load_name_parts` fallback mirrors `_specs`' own defensive
    # `if specs else` — it should be unreachable for an approved id, but an
    # empty `specs` must still render a name, not raise.
    if specs:
        name = naming_service.render_name(specs[0].parts, min_level=NameLevel.YEAR_RANGE)
    else:
        parts = await naming_service.load_name_parts(session, [motorbike.id])
        name = naming_service.render_name(parts[motorbike.id], min_level=NameLevel.YEAR_RANGE)

    return CatalogueModelDocument(
        data=CatalogueModelResource(
            id=motorbike.id,
            attributes=CatalogueModelAttributes(
                name=name,
                manufacturer=_manufacturer_name(motorbike.manufacturer_id, manufacturers),
                specs=_specs(specs[0].values if specs else None),
                article=_article(documents),
                sources=_sources(documents),
                images=_images(images),
                variants=_variants(motorbike),
            ),
        )
    )
