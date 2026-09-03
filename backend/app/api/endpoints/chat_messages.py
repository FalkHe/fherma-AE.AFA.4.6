"""The `chat-messages` resource: the timeline of one consultation.

Customer surface like `chats`: `current_user`, and `csrf_protect` on the write.
Ownership is checked through `chat_service.get_owned_chat` before a single
message is read or written, so a foreign, unknown or soft-deleted consultation
answers `404 not-found` here too — the messages of a deleted consultation are
unreachable without deleting a row.

`filter[chat]` is **required** on the list: a message only means something
inside its conversation, and there is no use case for reading every message of
every consultation. Ordering is the pinned timeline (`created_at ASC, id ASC`,
owned by `chat_service`) — the reverse of the admin lists, because a
conversation reads top to bottom.

`POST` persists the customer's message **and starts the advisor's turn**, so the
response carries the stored message while `activeOperationId` is set on the
consultation. A second message while a turn is genuinely in flight is
`409 response-pending`; a turn that was lost (a killed worker, a crash between
two commits) heals instead of blocking — see `chat_service.heal_stale_turn`. The
check runs *before* the message is stored: a rejected message must not stay
behind as a question the advisor will never see.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import jsonapi
from app.api.deps import csrf_protect, current_user
from app.api.schemas.chat_messages import (
    ChatMessageAttributes,
    ChatMessageCreateRequest,
    ChatMessageDocument,
    ChatMessageListDocument,
    ChatMessageResource,
)
from app.db.models.chat import Chat, ChatMessage
from app.db.models.user import User
from app.db.session import get_db_session
from app.services import chat_service

router = APIRouter(
    prefix="/chat-messages",
    tags=["chat-messages"],
    dependencies=[Depends(current_user)],
)

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]
UserDep = Annotated[User, Depends(current_user)]

CHAT_FILTER_DESCRIPTION = "ULID of the consultation whose messages to return (required)."


def _resource(message: ChatMessage) -> ChatMessageResource:
    """Project one message row onto a resource object.

    The three JSONB columns already hold the pinned camelCase shapes, so this is
    a projection, not a translation.
    """
    return ChatMessageResource(
        id=message.id, attributes=ChatMessageAttributes.model_validate(message)
    )


def _chat_id(raw: str | None) -> str:
    """Return the single consultation id `filter[chat]` carries.

    Absent is a client error rather than "everything": the whole message corpus
    of an account is not a use case, and answering it would ship every
    conversation at once.
    """
    members = jsonapi.parse_filter(raw)
    if members is None:
        raise jsonapi.JsonApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="missing-filter",
            detail="filter[chat] is required: messages are listed per consultation.",
        )
    if len(members) != 1:
        raise jsonapi.JsonApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid-filter",
            detail="filter[chat] takes exactly one consultation id.",
        )
    return members[0]


async def _owned_chat_or_404(session: AsyncSession, user: User, chat_id: str) -> Chat:
    """Load the signed-in account's live consultation, or fail with 404.

    Same collapse as the `chats` resource: unknown, foreign and deleted are one
    answer, so a message list cannot reveal what a consultation list hides.
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
    response_model=ChatMessageListDocument,
    summary="List the messages of one consultation",
    responses=jsonapi.error_responses(status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND),
)
async def list_chat_messages(
    session: SessionDep,
    user: UserDep,
    page: jsonapi.PaginationDep,
    chat_filter: Annotated[
        str | None,
        Query(alias="filter[chat]", description=CHAT_FILTER_DESCRIPTION),
    ] = None,
) -> ChatMessageListDocument:
    """Return one page of a consultation's timeline, oldest message first.

    The page is cut from the timeline in the route: `chat_service.list_messages`
    loads a whole conversation in one query — a bounded, per-account amount of
    text the agent loop replays in full anyway — so paging here keeps that one
    pinned ordering as the single source of truth instead of duplicating it in a
    second, paginated query. `meta.totalCount` stays the length of the whole
    timeline, so the SPA can walk pages.
    """
    chat = await _owned_chat_or_404(session, user, _chat_id(chat_filter))
    messages = await chat_service.list_messages(session, chat.id)
    window = messages[page.offset : page.offset + page.limit]

    return ChatMessageListDocument(
        data=[_resource(message) for message in window],
        meta=jsonapi.Meta(total_count=len(messages)),
    )


@router.post(
    "",
    response_model=ChatMessageDocument,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(csrf_protect)],
    summary="Send a message to the advisor",
    responses=jsonapi.error_responses(status.HTTP_404_NOT_FOUND, status.HTTP_409_CONFLICT),
)
async def create_chat_message(
    session: SessionDep, user: UserDep, payload: ChatMessageCreateRequest
) -> ChatMessageDocument:
    """Persist the customer's message and start the advisor's answer.

    The body arrives stripped, non-empty and bounded from the request schema —
    `chat_service.append_user_message` stores it verbatim and names the
    consultation from it when it is still unnamed.

    The stale-turn check comes first, because its refusal is a refusal of the
    message: an in-flight turn built its context before this request arrived, so
    a message stored next to it would never be answered.
    """
    attributes = payload.data.attributes
    chat = await _owned_chat_or_404(session, user, attributes.chat_id)
    if not await chat_service.heal_stale_turn(session, chat):
        raise jsonapi.JsonApiError(
            status_code=status.HTTP_409_CONFLICT,
            code="response-pending",
            detail="The advisor is still answering the previous message.",
        )

    message = await chat_service.append_user_message(session, chat, attributes.body)
    await chat_service.start_response(session, chat)
    # `created_at` is a server default: read it back rather than risking
    # implicit IO while rendering.
    await session.refresh(message)
    return ChatMessageDocument(data=_resource(message))
