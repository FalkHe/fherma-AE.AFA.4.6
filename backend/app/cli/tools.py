"""`app tools` — run one advisor tool from the command line.

`app tools run spec_comparison --args '{"names":["Honda CB500F","Suzuki GSR600"]}'`
executes exactly what the agent loop executes (`llm.agents.tools.execute`, args
schema and collector included) and prints the pinned result. It is the harness for
judging a tool on real data without a browser, an LLM or a consultation: what it
prints is byte-for-byte what lands in `chat_messages.tool_calls[].result` and what
the chat UI renders.

Conventions of `app.cli.rag` / `app.cli.retrieval`: the Typer body stays
synchronous and calls `asyncio.run(...)`, the async half opens one session and
only goes through the tool layer, and an expected failure is a message on stderr
with exit code 1 instead of a traceback.
"""

import asyncio
import json
from typing import Annotated, Any, NoReturn

import typer
from pydantic import ValidationError

from app.db.session import get_sessionmaker
from app.llm.agents import tools
from app.llm.agents.tools import spec_comparison

app = typer.Typer(
    help="Run the advisor's tools directly.",
    no_args_is_help=True,
    add_completion=False,
)

# Rendered for a `null` value, as the UI does: a missing verified number is shown
# as a gap, never as a blank cell that could pass for zero.
UNKNOWN = "—"


@app.callback()
def root() -> None:
    """Keep sub-commands addressable by name, even when only one exists."""


@app.command("run")
def run(
    tool_name: Annotated[str, typer.Argument(help="Which registered tool to run.")],
    args: Annotated[
        str,
        typer.Option("--args", help="The tool arguments as a JSON object."),
    ] = "{}",
) -> None:
    """Execute one tool and print its result.

    The tool's own args schema validates `--args`, so a wrong argument fails here
    exactly as it would fail for the model.
    """
    try:
        spec = tools.get_tool_spec(tool_name)
    except KeyError:
        _fail(f"Unknown tool {tool_name!r}. Registered: {', '.join(tools.tool_names())}.")

    arguments = _parse_arguments(args)

    try:
        payload = asyncio.run(_run(spec, arguments))
    except ValidationError as error:
        _fail(f"Invalid arguments for {tool_name}:\n{error}")

    if tool_name == spec_comparison.NAME and "rows" in payload:
        _print_comparison(payload)
        typer.echo("")
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))


async def _run(spec: tools.ToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
    """Async half of `run`: one session, one tool context, one call.

    `chat=None`: this harness answers nobody's consultation, so a tool that writes
    chat-scoped rows has to say so rather than inventing a chat.
    """
    async with get_sessionmaker()() as session:
        return await tools.execute(spec, tools.ToolContext(session=session), arguments)


def _parse_arguments(args: str) -> dict[str, Any]:
    """Parse `--args` into the argument object, or fail with a readable message."""
    try:
        arguments = json.loads(args)
    except json.JSONDecodeError as error:
        _fail(f"--args is not valid JSON: {error}")
    if not isinstance(arguments, dict):
        _fail('--args must be a JSON object, e.g. \'{"names": ["Honda CB500F"]}\'.')
    return arguments


def _print_comparison(payload: dict[str, Any]) -> None:
    """Print a `spec_comparison` result as the aligned table it describes.

    The one tool-specific rendering in this harness, and the reason is the step's
    verification: alignment and explicit nulls are the properties to eyeball, and
    JSON shows neither.
    """
    bikes = [bike["name"] for bike in payload["bikes"]]
    rows = [[row["field"], *(_cell(value) for value in row["values"])] for row in payload["rows"]]
    header = ["attribute", *bikes]
    widths = [max(len(row[column]) for row in [header, *rows]) for column in range(len(header))]

    for row in [header, *rows]:
        typer.echo("  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)))


def _cell(value: Any) -> str:
    """Render one table cell: `null` as the unknown marker, everything else plainly."""
    if value is None:
        return UNKNOWN
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _fail(message: str) -> NoReturn:
    """Report an expected failure on stderr and exit non-zero."""
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
