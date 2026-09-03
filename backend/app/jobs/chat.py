"""`chat.respond` — the task that answers one consultation turn.

Thin like every task here: ids only, its own session, and the `operations` row
created before the enqueue is the state the browser watches. What an answer *is*
lives in `chat_response_service.generate` — the seam step 3.13 replaces with the
tool-calling loop, without this module changing.

Failure policy, and it is the point of this file:

* A gateway **timeout** is transient: `TransientJobError` propagates, the
  broker retries, and the operation stays `running` — the customer keeps seeing
  the advisor type, because the very same turn is about to be attempted again.
* **Anything else ends the turn visibly.** The apologetic assistant message is
  persisted (which clears `active_operation_id` and announces the message, like
  any reply) and the operation is marked `failed` with the technical detail for
  an admin. Never a silent dead chat: a consultation that stops answering
  without saying so is indistinguishable from a broken product.
* A deleted consultation is nobody's turn any more: the operation is failed and
  nothing is written.
"""

import logging

from openai import APIConnectionError, APITimeoutError
from openrouter.errors import EdgeNetworkTimeoutResponseError, RequestTimeoutResponseError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.jobs import TransientJobError
from app.jobs.broker import broker
from app.services import chat_response_service, chat_service, operation_service

logger = logging.getLogger(__name__)

# The reply the customer reads when the turn failed. Deliberately plain and
# actionable: the technical detail belongs on the operation, not in the chat.
APOLOGY = (
    "I am sorry — something went wrong while I was preparing your answer. "
    "Please send your message again."
)

# Gateway timeouts and connection failures, and only those, are worth
# retrying: the request never reached a completion, so repeating it is not a
# second answer. Everything else (authentication, a rejected request, a bug
# here) would fail again identically. The `openrouter` pair covers
# `ChatOpenRouter` (the advisor's own model calls); the `openai` pair covers
# `OpenAIEmbeddings` (the retrieval tool's embedding calls, `llm/embeddings.py`)
# — `langchain_openai` talks to OpenRouter through the OpenAI SDK, whose
# transport errors are these types, not the `openrouter` package's.
TRANSIENT_GATEWAY_ERRORS = (
    EdgeNetworkTimeoutResponseError,
    RequestTimeoutResponseError,
    APITimeoutError,
    APIConnectionError,
)

# What an admin reads on the operation when the consultation is gone.
CHAT_GONE_ERROR = "The consultation was deleted before the answer was ready."

# How much of the exception reaches the operation's `error` column.
MAX_ERROR_CHARS = 500


@broker.task("chat.respond", retry_on_error=True)
async def respond(chat_id: str, operation_id: str) -> None:
    """Answer the current turn of `chat_id`, reporting into `operation_id`.

    Args:
        chat_id: The consultation whose stored timeline is the context.
        operation_id: Its `queued` operation row, created before the enqueue.
    """
    async with get_sessionmaker()() as session:
        operation = await operation_service.get(session, operation_id)
        if operation is None:
            # Nothing to report into; a retry would find the same missing row.
            logger.error("chat.respond: unknown operation %r — nothing to do.", operation_id)
            return

        chat = await chat_service.get_chat(session, chat_id)
        if chat is None:
            logger.warning(
                "chat.respond: consultation %r is gone; operation %s abandoned.",
                chat_id,
                operation_id,
            )
            await operation_service.fail(session, operation, CHAT_GONE_ERROR)
            return

        await operation_service.start(session, operation)
        try:
            await chat_response_service.generate(session, chat, operation)
        except TRANSIENT_GATEWAY_ERRORS as error:
            logger.warning(
                "chat.respond for chat %s hit a gateway timeout; retrying: %s", chat_id, error
            )
            raise TransientJobError(str(error)) from error
        except Exception as error:
            logger.exception("chat.respond for chat %s failed.", chat_id)
            # The exception may have left a broken transaction behind; the
            # bookkeeping below needs a usable session.
            await session.rollback()
            await _apologize(session, chat_id, operation_id, error)
            return

        await operation_service.succeed(session, operation)


async def _apologize(
    session: AsyncSession, chat_id: str, operation_id: str, error: Exception
) -> None:
    """Close a failed turn: the apology to the customer, the reason to the admin.

    **Ids, not rows, and both are re-loaded here**: `Session.rollback()` expires
    every instance it holds, so touching an attribute of the objects the caller
    was holding would be implicit IO — fatal on an async session, and it would
    cost the customer the apology they are owed.

    The message goes first, because appending it is what clears the pointer and
    releases the typing indicator; the operation then carries the detail. Should
    the apology itself fail to persist, the operation is still marked `failed`,
    so a dead turn is never invisible in the admin UI.
    """
    detail = f"{type(error).__name__}: {error}"[:MAX_ERROR_CHARS]

    chat = await chat_service.get_chat(session, chat_id)
    if chat is not None:
        try:
            await chat_service.append_assistant_message(session, chat, APOLOGY)
        except Exception:
            logger.exception("chat.respond: the apology for chat %s could not be stored.", chat_id)
            await session.rollback()

    # Loaded last, so that a rollback above cannot leave it expired either.
    operation = await operation_service.get(session, operation_id)
    if operation is None:  # pragma: no cover - it existed moments ago
        logger.error("chat.respond: operation %r vanished mid-turn.", operation_id)
        return
    await operation_service.fail(session, operation, detail)
