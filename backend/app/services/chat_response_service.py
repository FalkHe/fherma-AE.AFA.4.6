"""How the advisor answers one turn — the seam between the job and the agent.

`generate` is the whole of a response turn: run the agent loop, persist what it
produced. It stayed a service function through step 3.13's rewrite for one
reason — `app.jobs.chat` and the routes around it never had to change, so the
failure policy, the operation lifecycle and the enqueue seam are still owned by
the code that owned them before the advisor learned to use tools.

Two rules live here:

* **The turn is rebuilt from the database, not from a cache.** The context
  (timeline body-only, active preferences) is assembled by
  `app.llm.agents.advisor` on every turn, so a worker restart, a second worker or
  a reload mid-answer all see the same conversation. Persistence *is* the
  resumability story.
* **The reply is persisted in exactly one place**:
  `chat_service.append_assistant_message`, which ends the turn (clears
  `active_operation_id`) and announces the message. The three traces the agent
  produced — tool calls, sources, recommendation snapshots — are already in their
  pinned camelCase shapes and are stored verbatim. Nothing here writes a message
  row or an event itself, and nothing here decides what a tool call looks like.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Chat, ChatMessage
from app.db.models.operation import Operation
from app.llm.agents import advisor
from app.services import chat_service

logger = logging.getLogger(__name__)


class EmptyAnswerError(RuntimeError):
    """The model returned no text at all.

    A dedicated failure rather than an empty bubble: the job turns any exception
    into the apologetic message, and an empty assistant message would look like
    a delivered answer while saying nothing. The turn's tool calls are lost with
    it — deliberately, since they would be a message the customer cannot read.
    """

    def __init__(self) -> None:
        super().__init__("The advisor model returned an empty answer.")


async def generate(session: AsyncSession, chat: Chat, operation: Operation) -> ChatMessage:
    """Answer the current turn of `chat` and persist the reply.

    Args:
        session: Session the reads and the write go through; the append commits.
        chat: The consultation being answered; its stored timeline and captured
            preferences are the context.
        operation: The `running` operation this turn reports into. Not written
            to here — the job owns the lifecycle — but named in the log.

    Returns:
        The stored assistant message, with the turn's tool calls, sources and
        recommendations.

    Raises:
        EmptyAnswerError: The model answered with no text.
        TimeoutError: The turn exceeded `AGENT_TIMEOUT_SECONDS`.
        MissingApiKeyError: `OPENROUTER_API_KEY` is not configured.
        Exception: Anything the gateway call raises reaches the caller — the job
            decides which failures are retried and which become an apology.
    """
    logger.info("chat %s: answering turn %s.", chat.id, operation.id)
    result = await advisor.run_advisor_turn(session, chat)

    if not result.body:
        raise EmptyAnswerError

    return await chat_service.append_assistant_message(
        session,
        chat,
        result.body,
        tool_calls=result.tool_calls,
        sources=result.sources,
        recommendations=result.recommendations,
    )
