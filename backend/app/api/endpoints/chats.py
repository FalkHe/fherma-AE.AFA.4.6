"""The `chats` resource: the customer's own consultations.

The first non-admin surface of the API: `current_user`, **not** `current_admin`
— admins are users too, and a consultation belongs to whoever started it. Every
write additionally carries `csrf_protect`.

Two rules govern this module, and both come from `chat_service`:

* **Ownership is invisible.** A foreign consultation, an unknown id and a
  soft-deleted one are all `404 not-found`. `get_owned_chat` collapses the three
  into `None` on purpose, so no route here can leak whether an id exists.
* **DELETE is a soft delete.** It sets `deleted_at` and answers 204; deleting
  the same consultation twice therefore answers 404, and there is no un-delete
  endpoint (restoring is a database operation).

There is no PATCH: nothing about a consultation is user-editable this phase (the
title comes from the first user message).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import jsonapi
from app.api.deps import csrf_protect, current_user
from app.api.schemas.chats import (
    ChatAttributes,
    ChatCreateRequest,
    ChatDocument,
    ChatListDocument,
    ChatResource,
)
from app.db.models.chat import Chat
from app.db.models.user import User
from app.db.session import get_db_session
from app.services import chat_service

router = APIRouter(
    prefix="/chats",
    tags=["chats"],
    dependencies=[Depends(current_user)],
)

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
UserDep = Annotated[User, Depends(current_user)]
ChatIdDep = Annotated[str, Path(description="ULID of the consultation.")]


def _resource(chat: Chat) -> ChatResource:
    """Project one consultation row onto a resource object."""
    return ChatResource(id=chat.id, attributes=ChatAttributes.model_validate(chat))


async def _get_or_404(session: AsyncSession, user: User, chat_id: str) -> Chat:
    """Load the signed-in account's live consultation, or fail with 404.

    Not found, not yours and deleted are one answer — see the module docstring.
    """
    chat = await chat_service.get_owned_chat(session, chat_id, user.id)
    if chat is None:
        raise jsonapi.JsonApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not-found",
            detail=f"No consultation with id '{chat_id}'.",
        )
    return chat


@router.get(
    "",
    response_model=ChatListDocument,
    summary="List the signed-in account's consultations",
)
async def list_chats(
    session: SessionDep, user: UserDep, page: jsonapi.PaginationDep
) -> ChatListDocument:
    """Return one page of the customer's consultations, most recent activity first.

    The pinned sort deviation from the admin lists: `-updatedAt`, not
    `-createdAt` — a customer looks for the conversation they were just having.
    Deleted consultations are absent.
    """
    chats, total = await chat_service.list_chats(
        session, user.id, limit=page.limit, offset=page.offset
    )

    return ChatListDocument(
        data=[_resource(chat) for chat in chats],
        meta=jsonapi.Meta(total_count=total),
    )


@router.get(
    "/{chat_id}",
    response_model=ChatDocument,
    summary="Read one consultation",
    responses=jsonapi.error_responses(status.HTTP_404_NOT_FOUND),
)
async def get_chat(session: SessionDep, user: UserDep, chat_id: ChatIdDep) -> ChatDocument:
    """Return one of the customer's own, live consultations."""
    return ChatDocument(data=_resource(await _get_or_404(session, user, chat_id)))


@router.post(
    "",
    response_model=ChatDocument,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_protect)],
    summary="Start a consultation",
)
async def create_chat(
    session: SessionDep, user: UserDep, payload: ChatCreateRequest
) -> ChatDocument:
    """Create an empty consultation for the signed-in account and let the advisor open it.

    The request body carries an empty attributes object: there is nothing to
    supply, the title is derived later from the first user message, and a
    consultation is only ever created by an explicit request — never on page
    load. The payload is therefore never read — validating it is the point, so
    an invented attribute is a 422 instead of a silently ignored key.

    The advisor speaks first: a response turn is started immediately, so the
    201 already carries `activeOperationId` and the greeting arrives over SSE as
    an ordinary assistant message. It does not name the consultation — the title
    still comes from the first *user* message.
    """
    chat = await chat_service.create_chat(session, user.id)
    await chat_service.start_response(session, chat)
    # Both timestamps are server defaults: read them back from the database
    # rather than risking implicit IO while rendering.
    await session.refresh(chat)
    return ChatDocument(data=_resource(chat))


@router.delete(
    "/{chat_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(csrf_protect)],
    summary="Delete a consultation",
    responses=jsonapi.error_responses(status.HTTP_404_NOT_FOUND),
)
async def delete_chat(session: SessionDep, user: UserDep, chat_id: ChatIdDep) -> Response:
    """Soft-delete one of the customer's own consultations.

    The row and its messages stay in the database behind the ownership check,
    which is why a second DELETE answers 404. Nothing is announced over SSE:
    only the owner can see this list, and their own mutation invalidates it.
    """
    chat = await _get_or_404(session, user, chat_id)
    await chat_service.soft_delete_chat(session, chat)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
