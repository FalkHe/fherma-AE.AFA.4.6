"""Scripted advisor consultation over the real HTTP API — the phase's evidence.

Run it from inside the backend container while the stack is up:

    docker compose exec app-web python scripts/demo_conversation.py

It registers a throwaway account, opens a consultation, drives an eight-turn
interview against the live API (real OpenRouter, real worker) and then asserts
what the phase promises: the advisor speaks first, at least three *distinct*
tools were called, every recommendation card points at an approved catalogue
entry, retrieved knowledge arrived with sources, a bike the catalogue does not
know produced exactly one backlog row, and a second, freshly authenticated
client sees the identical timeline (resumability = persistence).

Two deliberate properties, because this script runs against the deliverable
database and a non-deterministic model:

* **It cleans up after itself.** The throwaway account (its consultation,
  messages and preferences follow by `ON DELETE CASCADE`), the chat's operation
  rows and the backlog row the interview created are removed in a `finally`
  block — including after a failed assertion. Rows that existed before the run
  are never touched. The deletes are plain statements rather than service calls
  because no delete service exists and this script is not the API layer; it must
  not grow one behind the routes' back.
* **Every turn may be retried once.** A gateway hiccup shows up as the job's
  apology message or as a turn that never finishes; a re-sent message is
  cheaper than a red demo. A second failure fails the run.

Nothing here is imported by the application: it is a script, not a module.
"""

import asyncio
import os
import secrets
import sys
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import httpx2
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.core.config import get_settings
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.db.models.operation import Operation
from app.db.models.user import User
from app.db.session import get_sessionmaker
from app.jobs.chat import APOLOGY
from app.services import product_service
from app.services.operation_service import CHAT_ENTITY_TYPE

# The API as seen from inside the container that serves it. Overridable so the
# same script can be pointed at a host-published port.
BASE_URL = os.environ.get("DEMO_BASE_URL", "http://127.0.0.1:8000")

# A model the curated catalogue does not know. Deliberately *not* "Yamaha MT-07":
# that name is already in the backlog, so flagging it would answer
# `already_known` and prove nothing about the insert.
UNCATALOGUED_BIKE = "Kawasaki Z650"

# How often the timeline is polled while a turn is in flight, and how long one
# turn may take before it counts as lost (the agent's own budget plus a margin
# for the queue, the model's last token and the message insert).
POLL_INTERVAL_SECONDS = 2.0
TURN_MARGIN_SECONDS = 60.0

# Page size for the timeline walk (the API's maximum).
PAGE_SIZE = 100

RULE = "─" * 78


class DemoFailure(Exception):
    """A demo assertion failed, or a turn could not be completed."""


# --- the transcript -----------------------------------------------------------


@dataclass(frozen=True)
class Message:
    """One row of the consultation timeline, as the API returns it."""

    id: str
    role: str
    body: str
    tool_calls: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]

    @classmethod
    def from_resource(cls, resource: dict[str, Any]) -> "Message":
        attributes = resource["attributes"]
        return cls(
            id=resource["id"],
            role=attributes["role"],
            body=attributes["body"],
            tool_calls=attributes["toolCalls"],
            sources=attributes["sources"],
            recommendations=attributes["recommendations"],
        )

    @property
    def tool_names(self) -> list[str]:
        return [call["tool"] for call in self.tool_calls]

    @property
    def is_apology(self) -> bool:
        return self.role == "assistant" and self.body.strip() == APOLOGY


def tool_names_of(messages: Iterable[Message]) -> list[str]:
    """Return every tool name called across `messages`, in order."""
    return [name for message in messages for name in message.tool_names]


# --- the API client -----------------------------------------------------------


class ApiClient:
    """A signed-in HTTP client: cookie jar plus the CSRF header on every write."""

    def __init__(self, client: httpx2.AsyncClient) -> None:
        self._client = client

    @property
    def _write_headers(self) -> dict[str, str]:
        """Mirror the CSRF cookie into the header, exactly as the SPA does."""
        token = self._client.cookies.get(CSRF_COOKIE_NAME)
        if token is None:
            raise DemoFailure("No CSRF cookie: the client is not signed in.")
        return {CSRF_HEADER_NAME: token}

    async def register(self, username: str, password: str) -> None:
        response = await self._client.post(
            "/auth/register", json={"username": username, "password": password}
        )
        _expect(response, 201, "register")

    async def login(self, username: str, password: str) -> str:
        response = await self._client.post(
            "/auth/login",
            json={"username": username, "password": password, "rememberMe": False},
        )
        _expect(response, 200, "login")
        return str(response.json()["id"])

    async def logout(self) -> None:
        response = await self._client.post("/auth/logout", headers=self._write_headers)
        _expect(response, 204, "logout")

    async def create_chat(self) -> dict[str, Any]:
        response = await self._client.post(
            "/api/chats",
            headers=self._write_headers,
            json={"data": {"type": "chats", "attributes": {}}},
        )
        _expect(response, 201, "create chat")
        return dict(response.json()["data"])

    async def get_chat(self, chat_id: str) -> dict[str, Any]:
        response = await self._client.get(f"/api/chats/{chat_id}")
        _expect(response, 200, "read chat")
        return dict(response.json()["data"])

    async def delete_chat(self, chat_id: str) -> None:
        response = await self._client.delete(f"/api/chats/{chat_id}", headers=self._write_headers)
        _expect(response, 204, "delete chat")

    async def send_message(self, chat_id: str, body: str) -> Message:
        response = await self._client.post(
            "/api/chat-messages",
            headers=self._write_headers,
            json={
                "data": {
                    "type": "chat-messages",
                    "attributes": {"chatId": chat_id, "body": body},
                }
            },
        )
        _expect(response, 201, "send message")
        return Message.from_resource(response.json()["data"])

    async def list_messages(self, chat_id: str) -> list[Message]:
        """Walk every page of one consultation's timeline, oldest first."""
        messages: list[Message] = []
        page = 1
        while True:
            response = await self._client.get(
                "/api/chat-messages",
                params={
                    "filter[chat]": chat_id,
                    "page[number]": page,
                    "page[size]": PAGE_SIZE,
                },
            )
            _expect(response, 200, "list messages")
            document = response.json()
            messages.extend(Message.from_resource(item) for item in document["data"])
            if len(messages) >= document["meta"]["totalCount"] or not document["data"]:
                return messages
            page += 1


def _expect(response: httpx2.Response, status_code: int, what: str) -> None:
    """Fail the run with the server's own words when a call did not succeed."""
    if response.status_code != status_code:
        raise DemoFailure(
            f"{what}: expected HTTP {status_code}, got {response.status_code} — {response.text}"
        )


# --- the scripted interview ---------------------------------------------------

CheckFn = Callable[[list[Message]], Awaitable[bool]]


@dataclass(frozen=True)
class Turn:
    """One scripted customer message plus what the reply has to show."""

    body: str
    expectation: str = ""
    check: CheckFn | None = None


async def _used_catalogue_search(replies: list[Message]) -> bool:
    return "catalogue_search" in tool_names_of(replies)


async def _cited_retrieved_knowledge(replies: list[Message]) -> bool:
    return "retrieve_bike_knowledge" in tool_names_of(replies) and any(
        message.sources for message in replies
    )


async def _backlog_row_exists(_replies: list[Message]) -> bool:
    """Consent turn: the flag may already have happened one turn earlier."""
    return await _flagged_motorbike_id() is not None


async def _presented_recommendations(replies: list[Message]) -> bool:
    return any(message.recommendations for message in replies)


TURNS: tuple[Turn, ...] = (
    Turn("Hi! I passed my A2 test last month and this would be my first own bike."),
    Turn(
        "I ride to work almost every day, about 20 km each way through city "
        "traffic, plus the occasional Sunday tour."
    ),
    Turn(
        "I am 1.72 m tall with an inside leg of roughly 80 cm, and I would like "
        "to stay around 6000 euro."
    ),
    Turn(
        "What does your catalogue actually have for someone like me?",
        expectation="the catalogue was searched",
        check=_used_catalogue_search,
    ),
    Turn(
        "What do reviews and owner reports say about the Honda CB500F?",
        expectation="knowledge was retrieved and sources were attached",
        check=_cited_retrieved_knowledge,
    ),
    Turn(
        f"A colleague keeps telling me to look at the {UNCATALOGUED_BIKE}. What do you make of it?"
    ),
    Turn(
        f"Yes please, note the {UNCATALOGUED_BIKE} down for your buyers.",
        expectation=f"{UNCATALOGUED_BIKE} reached the backlog",
        check=_backlog_row_exists,
    ),
    # Deliberately not "which *two* bikes": the dev catalogue holds a single
    # A2-eligible model, and asking for a number the data cannot supply makes the
    # advisor search again instead of showing what it has (observed twice).
    Turn(
        "Alright — please show me your shortlist, even if it is only one bike.",
        expectation="recommendation cards were presented",
        check=_presented_recommendations,
    ),
)


# --- database side (snapshot, probes, cleanup) --------------------------------


async def _approved_motorbike_ids() -> set[str]:
    """Every approved catalogue id — the set a recommendation may point at."""
    async with get_sessionmaker()() as session:
        motorbikes, _total = await product_service.list_motorbikes(
            session, statuses=[MotorbikeStatus.APPROVED], limit=PAGE_SIZE, offset=0
        )
        return {motorbike.id for motorbike in motorbikes}


async def _motorbike_ids() -> set[str]:
    """Every catalogue row id, whatever its status (the before/after snapshot)."""
    async with get_sessionmaker()() as session:
        result = await session.execute(select(Motorbike.id))
        return set(result.scalars().all())


async def _flagged_motorbike_id() -> str | None:
    """The id of the backlog row the interview's unknown bike would create."""
    async with get_sessionmaker()() as session:
        motorbike = await product_service.get_by_slug(
            session, product_service.slugify(UNCATALOGUED_BIKE)
        )
        return None if motorbike is None else motorbike.id


async def _delete_rows(
    session: AsyncSession,
    *,
    user_id: str | None,
    chat_id: str | None,
    motorbike_id: str | None,
) -> None:
    """Remove exactly what this run created, and nothing else."""
    if chat_id is not None:
        # Operations carry no foreign key to the chat, so cascade cannot reach them.
        await session.execute(
            delete(Operation).where(
                Operation.entity_type == CHAT_ENTITY_TYPE, Operation.entity_id == chat_id
            )
        )
    if user_id is not None:
        # Chats, messages, preferences and sessions follow ON DELETE CASCADE.
        await session.execute(delete(User).where(User.id == user_id))
    if motorbike_id is not None:
        await session.execute(delete(Motorbike).where(Motorbike.id == motorbike_id))
    await session.commit()


# --- the run ------------------------------------------------------------------


@dataclass
class Run:
    """Everything the assertions and the cleanup need to know about one run."""

    chat_id: str = ""
    user_id: str = ""
    greeting: Message | None = None
    timeline: list[Message] = field(default_factory=list)
    created_motorbike_id: str | None = None
    retries: list[str] = field(default_factory=list)


async def _wait_for_idle(api: ApiClient, chat_id: str, timeout: float) -> dict[str, Any]:
    """Poll the consultation until no advisor turn is in flight."""
    deadline = time.monotonic() + timeout
    while True:
        chat = await api.get_chat(chat_id)
        if chat["attributes"]["activeOperationId"] is None:
            return chat
        if time.monotonic() >= deadline:
            raise DemoFailure(
                f"The advisor's turn did not finish within {timeout:.0f} s "
                "(the worker may be down)."
            )
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _await_replies(
    api: ApiClient, chat_id: str, known_ids: set[str], timeout: float
) -> list[Message]:
    """Wait for the assistant messages of one turn, in timeline order."""
    deadline = time.monotonic() + timeout
    while True:
        chat = await api.get_chat(chat_id)
        timeline = await api.list_messages(chat_id)
        replies = [
            message
            for message in timeline
            if message.role == "assistant" and message.id not in known_ids
        ]
        if replies and chat["attributes"]["activeOperationId"] is None:
            return replies
        if time.monotonic() >= deadline:
            raise DemoFailure(f"No reply within {timeout:.0f} s.")
        await asyncio.sleep(POLL_INTERVAL_SECONDS)


def _print_message(message: Message) -> None:
    """Print one timeline row the way a reader wants to read it."""
    who = "customer" if message.role == "user" else "advisor"
    print(f"\n{who} ▸ {message.body.strip()}")
    if message.tool_calls:
        rendered = ", ".join(f"{call['tool']}[{call['status']}]" for call in message.tool_calls)
        print(f"    tools: {rendered}")
    if message.sources:
        titles = ", ".join(source["sourceTitle"] for source in message.sources[:3])
        print(f"    sources: {len(message.sources)} — {titles}")
    if message.recommendations:
        names = ", ".join(item["name"] for item in message.recommendations)
        print(f"    cards: {names}")


async def _play_turn(api: ApiClient, run: Run, index: int, turn: Turn, timeout: float) -> None:
    """Send one scripted message, wait for the reply and enforce its expectation.

    One retry: a lost turn or an apology is a gateway hiccup, and a failed
    expectation is usually the model taking a different route through the same
    conversation. The second attempt is final.
    """
    for attempt in (1, 2):
        known_ids = {message.id for message in run.timeline}
        sent = await api.send_message(run.chat_id, turn.body)
        _print_message(sent)

        problem: str | None = None
        try:
            replies = await _await_replies(api, run.chat_id, known_ids, timeout)
        except DemoFailure as error:
            problem = str(error)
            await _wait_for_idle(api, run.chat_id, timeout)
            replies = []
        else:
            for reply in replies:
                _print_message(reply)
            if any(reply.is_apology for reply in replies):
                problem = "the advisor apologised (the turn failed upstream)"
            elif turn.check is not None and not await turn.check(replies):
                problem = f"expectation not met: {turn.expectation}"

        run.timeline = await api.list_messages(run.chat_id)
        if problem is None:
            return

        if attempt == 2:
            raise DemoFailure(f"Turn {index} failed twice — {problem}")
        note = f"turn {index}: {problem} — retrying once"
        run.retries.append(note)
        print(f"\n!! {note}")


async def _open_consultation(api: ApiClient, run: Run, timeout: float) -> None:
    """Create the consultation and wait for the advisor to speak first."""
    chat = await api.create_chat()
    run.chat_id = chat["id"]
    if chat["attributes"]["activeOperationId"] is None:
        raise DemoFailure("The new consultation started no advisor turn.")

    replies = await _await_replies(api, run.chat_id, set(), timeout)
    run.timeline = await api.list_messages(run.chat_id)
    if len(run.timeline) != 1 or run.timeline[0].role != "assistant":
        roles = [message.role for message in run.timeline]
        raise DemoFailure(f"Expected the greeting alone as the first message, got {roles}.")
    run.greeting = replies[0]
    print(f"\nconsultation {run.chat_id} opened")
    _print_message(run.greeting)


# --- the assertions -----------------------------------------------------------


def _check(results: list[tuple[bool, str]], passed: bool, description: str) -> None:
    results.append((passed, description))


async def _assert_everything(
    run: Run, before_ids: set[str], username: str, password: str
) -> list[tuple[bool, str]]:
    """Run every acceptance check and return them as (passed, description) rows."""
    results: list[tuple[bool, str]] = []
    assistant = [message for message in run.timeline if message.role == "assistant"]

    greeting_first = (
        run.greeting is not None
        and run.timeline[0].id == run.greeting.id
        and run.timeline[0].role == "assistant"
        and bool(run.greeting.body.strip())
    )
    _check(results, greeting_first, "the advisor greeted before any customer message")

    distinct_tools = sorted(set(tool_names_of(assistant)))
    _check(
        results,
        len(distinct_tools) >= 3,
        f"{len(distinct_tools)} distinct tools called: {', '.join(distinct_tools) or '—'}",
    )

    approved_ids = await _approved_motorbike_ids()
    cards = [item for message in assistant for item in message.recommendations]
    unapproved = sorted({item["name"] for item in cards if item["motorbikeId"] not in approved_ids})
    _check(
        results,
        bool(cards) and not unapproved,
        f"{len(cards)} recommendation card(s), all approved catalogue entries"
        + (f" — offenders: {', '.join(unapproved)}" if unapproved else ""),
    )

    retrievals = [
        message
        for message in assistant
        if any(
            call["tool"] == "retrieve_bike_knowledge"
            and call["status"] == "succeeded"
            and call["result"].get("snippets")
            for call in message.tool_calls
        )
    ]
    sourced = [message for message in retrievals if message.sources]
    _check(
        results,
        bool(retrievals) and len(sourced) == len(retrievals),
        f"{len(retrievals)} message(s) retrieved knowledge, {len(sourced)} carry sources",
    )

    after_ids = await _motorbike_ids()
    created = after_ids - before_ids
    run.created_motorbike_id = next(iter(created)) if len(created) == 1 else None
    flagged_id = await _flagged_motorbike_id()
    _check(
        results,
        created == ({flagged_id} if flagged_id is not None else set()) and len(created) == 1,
        f"exactly one backlog row created for {UNCATALOGUED_BIKE} "
        f"({len(created)} new catalogue row(s), pre-existing rows untouched)",
    )

    fresh = await _fresh_client_timeline(username, password, run.chat_id)
    same = [
        (
            message.id,
            message.role,
            message.body,
            len(message.tool_calls),
            len(message.sources),
            len(message.recommendations),
        )
        for message in run.timeline
    ] == [
        (
            message.id,
            message.role,
            message.body,
            len(message.tool_calls),
            len(message.sources),
            len(message.recommendations),
        )
        for message in fresh
    ]
    _check(
        results,
        same and len(fresh) == len(run.timeline),
        f"a freshly authenticated client re-reads all {len(fresh)} messages identically",
    )
    return results


async def _fresh_client_timeline(username: str, password: str, chat_id: str) -> list[Message]:
    """Sign in again on a new connection and re-read the consultation."""
    async with httpx2.AsyncClient(base_url=BASE_URL, timeout=30.0) as raw:
        api = ApiClient(raw)
        await api.login(username, password)
        await api.get_chat(chat_id)
        timeline = await api.list_messages(chat_id)
        await api.logout()
        return timeline


# --- entry point --------------------------------------------------------------


async def _cleanup(run: Run, before_ids: set[str]) -> None:
    """Leave the database as it was found, whatever happened above."""
    created = (await _motorbike_ids()) - before_ids
    if run.created_motorbike_id is None and len(created) == 1:
        run.created_motorbike_id = next(iter(created))

    async with get_sessionmaker()() as session:
        await _delete_rows(
            session,
            user_id=run.user_id or None,
            chat_id=run.chat_id or None,
            motorbike_id=run.created_motorbike_id,
        )
    removed = ["the throwaway account with its consultation"] if run.user_id else []
    if run.created_motorbike_id is not None:
        removed.append(f"the {UNCATALOGUED_BIKE} backlog row")
    if len(created) > 1:
        removed.append(f"!! {len(created)} new catalogue rows found, only one removed")
    print(f"\ncleanup: removed {', '.join(removed) if removed else 'nothing'}.")


async def main() -> int:
    """Drive the whole demo and report every assertion."""
    settings = get_settings()
    timeout = settings.agent_timeout_seconds + TURN_MARGIN_SECONDS
    username = f"demo316-{secrets.token_hex(6)}"
    password = secrets.token_urlsafe(16)

    print(RULE)
    print(f"advisor demo — {BASE_URL}, account {username}, turn budget {timeout:.0f} s")
    print(RULE)

    before_ids = await _motorbike_ids()
    run = Run()
    results: list[tuple[bool, str]] = []
    failure: str | None = None

    try:
        async with httpx2.AsyncClient(base_url=BASE_URL, timeout=30.0) as raw:
            api = ApiClient(raw)
            await api.register(username, password)
            run.user_id = await api.login(username, password)
            await _open_consultation(api, run, timeout)
            for index, turn in enumerate(TURNS, start=1):
                await _play_turn(api, run, index, turn, timeout)
            results = await _assert_everything(run, before_ids, username, password)
            await api.delete_chat(run.chat_id)
    except DemoFailure as error:
        failure = str(error)
    finally:
        await _cleanup(run, before_ids)

    print(f"\n{RULE}")
    for passed, description in results:
        print(f"{'PASS' if passed else 'FAIL'}  {description}")
    for note in run.retries:
        print(f"note  retried — {note}")
    if failure is not None:
        print(f"FAIL  {failure}")
    print(RULE)

    if failure is not None or not results or not all(passed for passed, _ in results):
        print("demo failed")
        return 1
    print("demo green")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
