"""The `products` resource: the admin's view of the motorcycle catalogue.

The whole router is admin-only (`current_admin`) and every write additionally
carries `csrf_protect` — this is an administrative surface, reads included.

Business rules stay in `product_service`: this module translates its exceptions
into the pinned JSON:API error codes (`duplicate-model`, `invalid-transition`)
and its rows into resource objects. In particular no status is ever assigned
here — only `product_service.transition` may change one, so the legal matrix
cannot be bypassed through the API.
"""

from collections.abc import Mapping, Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import jsonapi
from app.api.deps import csrf_protect, current_admin
from app.api.schemas.products import (
    DraftSpecRequest,
    IdentityRequest,
    ProductAttributes,
    ProductCreateRequest,
    ProductDocument,
    ProductListDocument,
    ProductPatchRequest,
    ProductResource,
    ProductSuggestion,
    ProductVariant,
    SpecAttributes,
)
from app.db.models.manufacturer import Manufacturer
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.db.models.motorbike_spec import MotorbikeSpec, SpecKind
from app.db.session import get_db_session
from app.services import manufacturer_service, naming_service, product_service
from app.services.naming_service import NameLevel, NameParts

router = APIRouter(
    prefix="/products",
    tags=["products"],
    dependencies=[Depends(current_admin)],
)

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
ProductIdDep = Annotated[str, Path(description="ULID of the product.")]

STATUS_FILTER_DESCRIPTION = "Comma-separated list of statuses: " + ", ".join(
    member.value for member in MotorbikeStatus
)


def _draft_spec_values(draft_spec: DraftSpecRequest) -> dict[str, Any]:
    """Turn the request model into the service's full-object value mapping.

    Field names are the frozen column names, so a plain dump is the contract —
    the schema is the boundary that keeps unknown keys out. The two vocabulary
    fields dump as `StrEnum` members, which are strings for the database.
    """
    return draft_spec.model_dump()


def _spec_attributes(spec: MotorbikeSpec | None) -> SpecAttributes | None:
    """Project one specification row, or `None` when the revision is absent."""
    return None if spec is None else SpecAttributes.model_validate(spec)


def _manufacturer_name(
    motorbike: Motorbike, manufacturers: Mapping[str, Manufacturer]
) -> str | None:
    """Return the display name of a row's brand, or `None` when it has none.

    `manufacturer` is a derived attribute since Phase 2b: the catalogue row
    carries only the foreign key, and the wire shape carries only the name.
    """
    if motorbike.manufacturer_id is None:
        return None
    manufacturer = manufacturers.get(motorbike.manufacturer_id)
    return None if manufacturer is None else manufacturer.name


async def _manufacturers_of(
    session: AsyncSession, motorbikes: Sequence[Motorbike]
) -> Mapping[str, Manufacturer]:
    """Load the brands of a whole page of catalogue rows in one query."""
    return await manufacturer_service.get_by_ids(
        session,
        [
            motorbike.manufacturer_id
            for motorbike in motorbikes
            if motorbike.manufacturer_id is not None
        ],
    )


def _variant_attributes(variants: Sequence[Mapping[str, Any]] | None) -> list[ProductVariant]:
    """Project a row's stored trims (D1/D2, §2.5).

    `None`, not just an empty list, guards against the in-memory test double's
    server-default gap (6.15's landed note: `motorbike.variants` can be `None`
    there, never in real Postgres).
    """
    return [ProductVariant.model_validate(variant) for variant in variants or []]


def _suggestion_attributes(suggestion: Mapping[str, Any] | None) -> ProductSuggestion | None:
    """Project the unverified claim JSONB, or `None` when the row has none (D6)."""
    return None if suggestion is None else ProductSuggestion.model_validate(suggestion)


def _resource(
    motorbike: Motorbike,
    specs: Mapping[SpecKind, MotorbikeSpec],
    manufacturers: Mapping[str, Manufacturer],
    name_parts: NameParts,
) -> ProductResource:
    """Project a catalogue row plus its specifications onto a resource object.

    `name` is the *rendered* name (D5/D10) — the admin surface renders at
    `MODEL` with no context (`docs/roadmap/model-naming-data-model.md` §5): an
    admin looks at one row at a time, so there is no page to disambiguate
    against. `queryName` next to it is the phrase the admin (or
    `flag_unknown_bike`) originally typed, shown verbatim as context.
    """
    return ProductResource(
        id=motorbike.id,
        attributes=ProductAttributes(
            name=naming_service.render_name(name_parts, min_level=NameLevel.MODEL),
            slug=motorbike.slug,
            query_name=motorbike.query_name,
            manufacturer=_manufacturer_name(motorbike, manufacturers),
            buildingline=motorbike.buildingline,
            model_name=motorbike.model_name,
            year_from=motorbike.year_from,
            year_to=motorbike.year_to,
            type_codes=list(motorbike.type_codes or []),
            variants=_variant_attributes(motorbike.variants),
            suggestion=_suggestion_attributes(motorbike.suggestion),
            status=motorbike.status,
            draft_spec=_spec_attributes(specs.get(SpecKind.DRAFT)),
            verified_spec=_spec_attributes(specs.get(SpecKind.VERIFIED)),
            created_at=motorbike.created_at,
            updated_at=motorbike.updated_at,
        ),
    )


async def _document(session: AsyncSession, motorbike: Motorbike) -> ProductDocument:
    """Build the single-resource document for one catalogue row."""
    specs = await product_service.get_specs(session, [motorbike.id])
    manufacturers = await _manufacturers_of(session, [motorbike])
    name_parts = await naming_service.load_name_parts(session, [motorbike.id])
    return ProductDocument(
        data=_resource(
            motorbike, specs.get(motorbike.id, {}), manufacturers, name_parts[motorbike.id]
        )
    )


async def _get_or_404(session: AsyncSession, product_id: str) -> Motorbike:
    """Load a catalogue row or fail with the pinned 404 error document."""
    motorbike = await product_service.get_motorbike(session, product_id)
    if motorbike is None:
        raise jsonapi.JsonApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not-found",
            detail=f"No product with id '{product_id}'.",
        )
    return motorbike


def _parse_status_filter(raw: str | None) -> list[MotorbikeStatus] | None:
    """Turn `filter[status]` into statuses; `None` means unfiltered."""
    members = jsonapi.parse_filter(raw)
    if members is None:
        return None

    try:
        return [MotorbikeStatus(member) for member in members]
    except ValueError as error:
        raise jsonapi.JsonApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid-filter",
            detail=f"{STATUS_FILTER_DESCRIPTION}.",
        ) from error


@router.get(
    "",
    response_model=ProductListDocument,
    summary="List products",
    responses=jsonapi.error_responses(status.HTTP_400_BAD_REQUEST),
)
async def list_products(
    session: SessionDep,
    page: jsonapi.PaginationDep,
    status_filter: Annotated[
        str | None,
        Query(alias="filter[status]", description=STATUS_FILTER_DESCRIPTION),
    ] = None,
) -> ProductListDocument:
    """Return one page of the catalogue, newest first."""
    statuses = _parse_status_filter(status_filter)
    motorbikes, total = await product_service.list_motorbikes(
        session, statuses=statuses, limit=page.limit, offset=page.offset
    )
    specs = await product_service.get_specs(session, [motorbike.id for motorbike in motorbikes])
    manufacturers = await _manufacturers_of(session, motorbikes)
    name_parts = await naming_service.load_name_parts(
        session, [motorbike.id for motorbike in motorbikes]
    )

    return ProductListDocument(
        data=[
            _resource(
                motorbike, specs.get(motorbike.id, {}), manufacturers, name_parts[motorbike.id]
            )
            for motorbike in motorbikes
        ],
        meta=jsonapi.Meta(total_count=total),
    )


@router.get(
    "/{product_id}",
    response_model=ProductDocument,
    summary="Read a product",
    responses=jsonapi.error_responses(status.HTTP_404_NOT_FOUND),
)
async def get_product(session: SessionDep, product_id: ProductIdDep) -> ProductDocument:
    """Return one product with both of its specification revisions."""
    motorbike = await _get_or_404(session, product_id)
    return await _document(session, motorbike)


@router.post(
    "",
    response_model=ProductDocument,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_protect)],
    summary="Add a product to the backlog",
    responses=jsonapi.error_responses(status.HTTP_409_CONFLICT),
)
async def create_product(session: SessionDep, payload: ProductCreateRequest) -> ProductDocument:
    """Create an entry from a display name and start ingesting it.

    Adding a model auto-starts its ingestion: the row is created in `backlog`,
    moved to `ingesting` and its job enqueued — every step committed before the
    next — so the answer already carries the state the admin backlog shows.
    """
    try:
        motorbike = await product_service.create_backlog(session, payload.data.attributes.name)
    except product_service.DuplicateModelError as error:
        raise jsonapi.JsonApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="duplicate-model",
            detail=f"A product with slug '{error.args[0]}' already exists.",
        ) from error

    await product_service.start_ingestion(session, motorbike)
    # The status change flushed the row, expiring the server-side `updated_at`
    # (see the PATCH handler): render from a fully loaded row.
    await session.refresh(motorbike)
    return await _document(session, motorbike)


async def _check_manufacturer_exists(session: AsyncSession, manufacturer_id: str | None) -> None:
    """Raise a request-validation 422 when `manufacturer_id` names no row.

    A plain FastAPI request-validation error (not a `JsonApiError`), so the
    body matches the standard `{"detail": [{"loc": …}]}` shape every other
    field-level 422 in this API uses — the frontend's `validationFields`
    helper reads `loc[-1]`. Existence needs a session, so it cannot live in a
    Pydantic validator; skipping this check would leave `assign_identity`'s own
    `ValueError` on an unknown id to become an unhandled 500.
    """
    if manufacturer_id is None:
        return
    manufacturers = await manufacturer_service.get_by_ids(session, [manufacturer_id])
    if manufacturer_id not in manufacturers:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "data", "attributes", "identity", "manufacturerId"),
                    "msg": f"Unknown manufacturer id '{manufacturer_id}'.",
                    "input": manufacturer_id,
                }
            ]
        )


async def _apply_identity(
    session: AsyncSession, motorbike: Motorbike, identity: IdentityRequest
) -> None:
    """Write `identity` through `assign_identity` (D2), the block's only writer.

    `manufacturer_id` existence is checked first (a field-pointer 422);
    `assign_identity` itself still full-object-replaces every field, so a
    request that clears the manufacturer (`manufacturerId: null`) goes
    straight through.
    """
    await _check_manufacturer_exists(session, identity.manufacturer_id)
    try:
        await product_service.assign_identity(
            session,
            motorbike,
            manufacturer_id=identity.manufacturer_id,
            buildingline=identity.buildingline,
            model_name=identity.model_name,
            year_from=identity.year_from,
            year_to=identity.year_to,
            type_codes=identity.type_codes,
            variants=[variant.model_dump() for variant in identity.variants],
        )
    except product_service.DuplicateModelError as error:
        raise jsonapi.JsonApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="duplicate-model",
            detail=f"A product with slug '{error.args[0]}' already exists.",
        ) from error


@router.patch(
    "/{product_id}",
    response_model=ProductDocument,
    dependencies=[Depends(csrf_protect)],
    summary="Update a product's identity, draft specification and/or status",
    responses=jsonapi.error_responses(
        status.HTTP_404_NOT_FOUND,
        status.HTTP_409_CONFLICT,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
    ),
)
async def update_product(
    session: SessionDep, product_id: ProductIdDep, payload: ProductPatchRequest
) -> ProductDocument:
    """Replace the identity block, the draft specification and/or the status.

    All three attributes are optional and applied **in this order — identity,
    then draft specification, then status (D2)** — so a request that fills a
    missing identity and approves in the same call has the identity already
    written when the D4 `IncompleteIdentityError` guard runs; reversing the
    order would make that request fail the guard even though it supplies
    everything needed. `identity` is a full-object replace through
    `product_service.assign_identity`, the block's only writer; the response is
    always rendered from the row *after* every requested change, so it carries
    the recomputed `slug`. A transition to `ingesting` is a retry: it
    re-enqueues the ingestion job server-side, so the UI only ever asks for the
    status it wants.
    """
    motorbike = await _get_or_404(session, product_id)
    attributes = payload.data.attributes

    if attributes.identity is not None:
        await _apply_identity(session, motorbike, attributes.identity)

    if attributes.draft_spec is not None:
        await product_service.upsert_draft_spec(
            session, motorbike.id, _draft_spec_values(attributes.draft_spec)
        )

    if attributes.status is not None:
        try:
            if attributes.status is MotorbikeStatus.INGESTING:
                await product_service.start_ingestion(session, motorbike)
            else:
                await product_service.transition(session, motorbike, attributes.status)
        except product_service.InvalidTransitionError as error:
            raise jsonapi.JsonApiError(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="invalid-transition",
                detail=str(error),
            ) from error
        except product_service.IncompleteIdentityError as error:
            raise jsonapi.JsonApiError(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                code="incomplete-identity",
                detail=str(error),
            ) from error

    # `motorbikes.updated_at` has a server-side `onupdate`, so SQLAlchemy
    # expires the attribute when the row is flushed. Reading it back while
    # rendering would be implicit IO — fatal on an async session — hence one
    # explicit refresh, which also puts the new timestamp into the response.
    await session.refresh(motorbike)
    return await _document(session, motorbike)
