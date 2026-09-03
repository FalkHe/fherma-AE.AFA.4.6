"""Schemas for the `product-images` resource.

Wire shape is pinned by `docs/roadmap/phase-2/shared-knowledge.md`: resource
type `product-images`, camelCase attributes, `status` the single writable one.

The `variants` object is **computed, never stored and never read from disk**:
the pinned path formula
`MEDIA_DIR/motorbikes/{motorbike_id}/{image_id}_{variant}.webp` makes every
variant URL a pure function of two ids, so rendering an image costs no
filesystem access. `original_path` stays server-side — the browser only ever
sees the three resized variants, served by the `/media` static mount.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.api.jsonapi import Document, JsonApiModel, ListDocument, Resource
from app.db.models.motorbike_image import ImageStatus

PRODUCT_IMAGE_TYPE = "product-images"

# Where the image variants are served from; mirrors the `/media` static mount.
MEDIA_URL_PREFIX = "/media"


class ImageVariants(JsonApiModel):
    """The three resized renditions of one image, as URLs.

    The field names *are* the variant names of the path formula, which is why
    they are spelled out rather than kept in a separate constant.
    """

    thumb: str
    card: str
    detail: str


def variant_urls(motorbike_id: str, image_id: str) -> ImageVariants:
    """Return the deterministic variant URLs of one image."""
    return ImageVariants(
        thumb=_variant_url(motorbike_id, image_id, "thumb"),
        card=_variant_url(motorbike_id, image_id, "card"),
        detail=_variant_url(motorbike_id, image_id, "detail"),
    )


def _variant_url(motorbike_id: str, image_id: str, variant: str) -> str:
    """Apply the pinned path formula to one variant."""
    return f"{MEDIA_URL_PREFIX}/motorbikes/{motorbike_id}/{image_id}_{variant}.webp"


class ProductImageAttributes(JsonApiModel):
    """The pinned attribute set of a product image."""

    source_url: str
    attribution: str | None
    status: ImageStatus
    variants: ImageVariants
    created_at: datetime


class ProductImageResource(Resource[ProductImageAttributes]):
    """A product-image resource object."""

    type: Literal["product-images"] = PRODUCT_IMAGE_TYPE


class ProductImageDocument(Document[ProductImageResource]):
    """Body of `PATCH` on a single product image."""


class ProductImageListDocument(ListDocument[ProductImageResource]):
    """Body of `GET /api/product-images`."""


class ProductImagePatchAttributes(JsonApiModel):
    """The one writable attribute of an image: its moderation state."""

    model_config = ConfigDict(extra="forbid")

    status: ImageStatus


class ProductImagePatchResource(BaseModel):
    """The resource object of an image update request."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["product-images"] = PRODUCT_IMAGE_TYPE
    attributes: ProductImagePatchAttributes


class ProductImagePatchRequest(BaseModel):
    """Body of `PATCH /api/product-images/{id}`."""

    model_config = ConfigDict(extra="forbid")

    data: ProductImagePatchResource
