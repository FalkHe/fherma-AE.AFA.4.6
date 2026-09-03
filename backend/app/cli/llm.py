"""`app llm` — smoke tools for the OpenRouter connection.

`app llm ping` proves the chat path end to end (configuration → prompt file →
LangChain → OpenRouter → reply); `app llm embeddings-smoke` proves the
embeddings route and, crucially, that the vectors it returns have the
`EMBEDDING_DIMENSIONS` the `chunks.embedding` column is built for. Both are
manual tools:
nothing in the test suite calls a real model.

Follows the CLI conventions of `app.cli.users` / `app.cli.ingest`: the Typer
command body stays synchronous and calls `asyncio.run(...)`, expected failures
are reported on stderr with exit code 1 instead of a traceback.
"""

import asyncio
from typing import Annotated, NoReturn

import httpx2
import openrouter
import typer
from langchain_core.messages import HumanMessage
from langchain_openrouter import ChatOpenRouter
from openrouter.errors import OpenRouterError

from app.core.config import get_settings
from app.llm.models import MissingApiKeyError, get_chat_model
from app.llm.prompts import render_prompt

app = typer.Typer(
    help="Check the OpenRouter connection (chat and embeddings).",
    no_args_is_help=True,
    add_completion=False,
)

# The word `app llm ping` asks the model to reply with.
PING_WORD = "pong"

# OpenRouter's own API base, taken from the SDK that ships with
# langchain-openrouter instead of being spelled out here.
OPENROUTER_API_BASE = openrouter.SERVERS[openrouter.SERVER_PRODUCTION]

# Generous, so a slow first token does not look like a broken key.
REQUEST_TIMEOUT_SECONDS = 60.0


@app.callback()
def root() -> None:
    """Keep sub-commands addressable by name, even when only one exists."""


@app.command()
def ping(
    model: Annotated[
        str | None,
        typer.Option(help="OpenRouter model id; defaults to CHAT_MODEL."),
    ] = None,
) -> None:
    """Send one trivial completion through OpenRouter and print the reply."""
    try:
        chat = get_chat_model(model)
    except MissingApiKeyError as error:
        _fail(f"{error} Set it in .env and retry.")

    typer.echo(f"Model: {chat.model_name}", err=True)
    try:
        reply = asyncio.run(_complete(chat))
    except OpenRouterError as error:
        # A rejected key, an unknown model or an exhausted account are answers
        # from OpenRouter, not bugs — report them as such.
        _fail(f"OpenRouter rejected the request: {error}")

    typer.echo(f"Reply: {reply}")


@app.command("embeddings-smoke")
def embeddings_smoke(
    model: Annotated[
        str | None,
        typer.Option(help="OpenRouter embedding model id; defaults to EMBEDDING_MODEL."),
    ] = None,
) -> None:
    """Embed one short text through OpenRouter and assert the vector size.

    A key/account sanity check for the route the knowledge base depends on: it
    fails loudly if OpenRouter returns anything other than the configured
    `EMBEDDING_DIMENSIONS` floats, because that number is the width of the
    `chunks.embedding` column.

    Deliberately a thin HTTPX call rather than `app.llm.embeddings`: this command
    checks the *route and the key*, so it must not depend on the wrapper it is
    the fallback diagnosis for.
    """
    settings = get_settings()
    if not settings.openrouter_api_key:
        _fail("OPENROUTER_API_KEY is not configured. Set it in .env and retry.")

    model = model or settings.embedding_model
    typer.echo(f"Model: {model}", err=True)
    vector = asyncio.run(_embed(model, settings.openrouter_api_key))
    if len(vector) != settings.embedding_dimensions:
        _fail(f"Expected {settings.embedding_dimensions} dimensions, got {len(vector)}.")

    typer.echo(f"Vector: {len(vector)} dimensions, first value {vector[0]}.")


async def _complete(chat: ChatOpenRouter) -> str:
    """Invoke the chat model once with the `ping` prompt and return its text."""
    prompt = render_prompt("ping", word=PING_WORD)
    response = await chat.ainvoke([HumanMessage(prompt)])
    return response.text.strip()


async def _embed(model: str, api_key: str) -> list[float]:
    """POST one input to OpenRouter's embeddings route and return the vector."""
    async with httpx2.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        try:
            response = await client.post(
                f"{OPENROUTER_API_BASE}/embeddings",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "input": "Suzuki GSR 600"},
            )
        except httpx2.HTTPError as error:
            _fail(f"Embeddings request failed: {error!r}")

    if response.status_code != httpx2.codes.OK:
        _fail(f"Embeddings request failed: HTTP {response.status_code} {response.text[:200]}")

    payload = response.json()
    try:
        return payload["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError):
        _fail(f"Unexpected embeddings response shape: {str(payload)[:200]}")


def _fail(message: str) -> NoReturn:
    """Report an expected failure on stderr and exit non-zero."""
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
