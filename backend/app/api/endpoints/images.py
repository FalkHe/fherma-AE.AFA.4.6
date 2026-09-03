"""The `product-images` resource: moderation of the downloaded pictures.

Two routes: the per-product list the review screen renders, and the `status`
PATCH an admin rejects (or approves) a single image with. Nothing else is
writable — the file itself, its source URL and its attribution come from
ingestion.

Business rules stay in `product_service`: the moderation matrix lives in
`LEGAL_IMAGE_TRANSITIONS` and is applied by `transition_image`, which also
publishes the pinned `product.updated` event, so a rejected image reaches the
other admin screens without a reload.

The whole router is admin-only (`current_admin`); the PATCH additionally
carries `csrf_protect`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import jsonapi
from app.api.deps import csrf_protect, current_admin
from app.api.schemas.images import (
    ProductImageAttributes,
    ProductImageDocument,
    ProductImageListDocument,
    ProductImagePatchRequest,
    ProductImageResource,
    variant_urls,
)
from app.db.models.motorbike_image import MotorbikeImage
from app.db.session import get_db_session
from app.services import product_service

router = APIRouter(
    prefix="/product-images",
    tags=["product-images"],
    dependencies=[Depends(current_admin)],
)

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
ImageIdDep = Annotated[str, Path(description="ULID of the image.")]

PRODUCT_FILTER_DESCRIPTION = "ULID of the product whose images to return."


def _resource(image: MotorbikeImage) -> ProductImageResource:
    """Project one image row onto a resource object, variant URLs included."""
    return ProductImageResource(
        id=image.id,
        attributes=ProductImageAttributes(
            source_url=image.source_url,
            attribution=image.attribution,
            status=image.status,
            # Deterministic from the two ids — no stored path, no disk access.
            variants=variant_urls(image.motorbike_id, image.id),
            created_at=image.created_at,
        ),
    )


def _product_id(raw: str | None) -> str | None:
    """Return the product id `filter[product]` carries; `None` means unfiltered."""
    members = jsonapi.parse_filter(raw)
    if members is None:
        return None
    if len(members) != 1:
        raise jsonapi.JsonApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid-filter",
            detail="filter[product] takes exactly one product id.",
        )
    return members[0]


async def _get_or_404(session: AsyncSession, image_id: str) -> MotorbikeImage:
    """Load an image row or fail with the pinned 404 error document."""
    image = await product_service.get_image(session, image_id)
    if image is None:
        raise jsonapi.JsonApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not-found",
            detail=f"No product image with id '{image_id}'.",
        )
    return image


@router.get(
    "",
    response_model=ProductImageListDocument,
    summary="List product images",
    responses=jsonapi.error_responses(status.HTTP_400_BAD_REQUEST),
)
async def list_product_images(
    session: SessionDep,
    product_filter: Annotated[
        str | None,
        Query(alias="filter[product]", description=PRODUCT_FILTER_DESCRIPTION),
    ] = None,
) -> ProductImageListDocument:
    """Return the images of one product (or of the whole catalogue), newest first.

    Unpaginated on purpose: ingestion stores at most one image per run, so a
    product has a handful of rows and the review screen renders the newest.
    """
    images = await product_service.list_images(session, motorbike_id=_product_id(product_filter))

    return ProductImageListDocument(
        data=[_resource(image) for image in images],
        meta=jsonapi.Meta(total_count=len(images)),
    )


@router.patch(
    "/{image_id}",
    response_model=ProductImageDocument,
    dependencies=[Depends(csrf_protect)],
    summary="Approve or reject a product image",
    responses=jsonapi.error_responses(
        status.HTTP_404_NOT_FOUND, status.HTTP_422_UNPROCESSABLE_CONTENT
    ),
)
async def update_product_image(
    session: SessionDep, image_id: ImageIdDep, payload: ProductImagePatchRequest
) -> ProductImageDocument:
    """Move one image to a new moderation state.

    Legal moves are pinned in `product_service.LEGAL_IMAGE_TRANSITIONS`;
    anything else — including a no-op — is a 422 `invalid-transition`.
    """
    image = await _get_or_404(session, image_id)

    try:
        await product_service.transition_image(session, image, payload.data.attributes.status)
    except product_service.InvalidImageTransitionError as error:
        raise jsonapi.JsonApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            code="invalid-transition",
            detail=str(error),
        ) from error

    return ProductImageDocument(data=_resource(image))
