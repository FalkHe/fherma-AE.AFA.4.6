"""The project's small internal JSON:API layer.

Documents follow the JSON:API 1.1 *structure* (`data` / `attributes` / `meta` /
`errors`) but are served as plain `application/json`: there is no content
negotiation and no third-party framework. This is a deliberate simplification —
the only client is the SPA's generated `openapi-fetch` client.

What lives here is what every `/api/*` resource shares:

* the response envelopes (`Document`, `ListDocument`, `Resource`, `Meta`),
  generic over a resource's attribute model so a resource module only writes its
  attributes and two thin subclasses;
* page-number pagination (`page[number]` / `page[size]`, default and maximum
  page size 100) as a FastAPI dependency;
* comma-separated `filter[...]` parsing;
* error objects — `JsonApiError` plus the handler that renders it, so the
  frontend can branch on **status code + `code`** and never on detail text.

**Relationships and `included` are deliberately absent**: no Phase-2 resource
needs them (operation state reaches the UI through `/api/operations`), so the
machinery is deferred until one does.

Scope of the error document: it covers the *domain* failures a resource raises
(`404 not-found`, `409 duplicate-model`, `422 invalid-transition`, …). Framework
level failures keep FastAPI's own bodies — request validation stays the default
`422 {"detail": [{"loc": …}]}` shape (the review form maps `loc` to fields) and
the auth/CSRF dependencies keep their `{"detail": "…"}` sentence.
"""

from dataclasses import dataclass
from http import HTTPStatus
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# Page size is both the default and the ceiling: the catalogue is small (~150
# rows) and list hooks walk pages via `meta.totalCount`.
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 100
# `page[number]` ceiling: comfortably beyond any real page count, just there to
# turn an absurd value into a 422 instead of a huge, wasted `OFFSET`.
MAX_PAGE_NUMBER = 10_000
# `filter[...]` caps: a comma-separated value is user input parsed before any
# vocabulary or type check runs, so it needs its own bound — an unbounded
# member count or member length could otherwise reach the SQL layer as an IN
# clause with thousands of entries.
MAX_FILTER_MEMBERS = 50
MAX_FILTER_MEMBER_LENGTH = 128


class JsonApiModel(BaseModel):
    """Base for models whose fields cross the wire: camelCase out, snake in."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Meta(JsonApiModel):
    """Top-level `meta` of a collection document."""

    total_count: int


class Resource[AttributesT: BaseModel](BaseModel):
    """A JSON:API resource object: identity plus attributes."""

    id: str
    type: str
    attributes: AttributesT


class Document[ResourceT: Resource](BaseModel):
    """A single-resource document."""

    data: ResourceT


class ListDocument[ResourceT: Resource](BaseModel):
    """A collection document; `meta.totalCount` is the unpaginated total."""

    data: list[ResourceT]
    meta: Meta


class ErrorObject(BaseModel):
    """One JSON:API error object.

    `status` is the HTTP status as a string (JSON:API requires that), `code` is
    the stable application code the frontend branches on, `detail` is an English
    sentence for developers and log lines — never parsed.
    """

    status: str
    code: str
    detail: str


class ErrorDocument(BaseModel):
    """The body of every failed request this layer produces."""

    errors: list[ErrorObject]


class JsonApiError(HTTPException):
    """A domain failure to render as an `ErrorDocument`.

    Subclasses `HTTPException` so raising it from anywhere in a route works and
    an unregistered handler still yields the right status code.
    """

    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.code = code


def error_document(status_code: int, code: str, detail: str) -> ErrorDocument:
    """Build the error document for a single failure."""
    return ErrorDocument(errors=[ErrorObject(status=str(status_code), code=code, detail=detail)])


async def json_api_error_handler(request: Request, exc: JsonApiError) -> JSONResponse:
    """Render a `JsonApiError` as a JSON:API error document."""
    document = error_document(exc.status_code, exc.code, str(exc.detail))
    return JSONResponse(status_code=exc.status_code, content=document.model_dump())


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """Return `responses=` entries documenting `ErrorDocument` for each status.

    Without this the generated client would type every failure as FastAPI's
    default `{"detail": …}` body.
    """
    return {
        status_code: {"model": ErrorDocument, "description": HTTPStatus(status_code).phrase}
        for status_code in status_codes
    }


@dataclass(frozen=True)
class Pagination:
    """A validated `page[number]` / `page[size]` pair."""

    number: int
    size: int

    @property
    def limit(self) -> int:
        return self.size

    @property
    def offset(self) -> int:
        return (self.number - 1) * self.size


def pagination(
    number: Annotated[
        int,
        Query(
            alias="page[number]",
            ge=1,
            le=MAX_PAGE_NUMBER,
            description=f"1-based page number (maximum {MAX_PAGE_NUMBER}).",
        ),
    ] = 1,
    size: Annotated[
        int,
        Query(
            alias="page[size]",
            ge=1,
            le=MAX_PAGE_SIZE,
            description=f"Rows per page (maximum {MAX_PAGE_SIZE}).",
        ),
    ] = DEFAULT_PAGE_SIZE,
) -> Pagination:
    """Page-number pagination as a dependency; out-of-range values give a 422."""
    return Pagination(number=number, size=size)


PaginationDep = Annotated[Pagination, Depends(pagination)]


def parse_filter(value: str | None) -> list[str] | None:
    """Split a comma-separated `filter[...]` value into its members.

    Returns `None` when the parameter is absent or carries no usable value, so
    callers can treat "not filtered" and "filtered by nothing" alike. A
    member count or member length beyond the module caps is a 400
    `invalid-filter` — the same code every vocabulary caller already raises
    for an unknown member, so this stays indistinguishable on the wire.
    """
    if value is None:
        return None
    members = [member.strip() for member in value.split(",") if member.strip()]
    if not members:
        return None
    if len(members) > MAX_FILTER_MEMBERS:
        raise JsonApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid-filter",
            detail=f"A filter may have at most {MAX_FILTER_MEMBERS} members.",
        )
    if any(len(member) > MAX_FILTER_MEMBER_LENGTH for member in members):
        raise JsonApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid-filter",
            detail=f"A filter member may be at most {MAX_FILTER_MEMBER_LENGTH} characters long.",
        )
    return members
