"""Interactive CLI session against a real run. Reply on stdout, rolls on stderr.
Maintains a persistent thread_id across turns within the session backed by the
checkpointer.
"""

import asyncio
import sys
import uuid
from pathlib import Path
from typing import Any

import typer
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.runnables import RunnableConfig

from app.core.checkpointer import service as checkpointer_service
from app.core.db import get_sessionmaker
from app.core.llm.errors import LlmError
from app.modules.game import service as game_service
from app.modules.game.agent.state import DmContext
from app.modules.playthrough.errors import PlaythroughError

game_app = typer.Typer()


async def _run_turn(
    agent,
    *,
    user_id: str,
    actor_id: str | None,
    run_id: str | None,
    thread_id: str,
    text: str,
) -> game_service.TurnResult:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        context = DmContext(
            db=db,
            user_id=user_id,
            actor_id=actor_id,
            run_id=run_id,
            turn_id=str(uuid.uuid4()),
        )
        return await game_service.turn(
            agent, thread_id=thread_id, context=context, player_text=text
        )


async def _resume_turn(
    agent,
    *,
    user_id: str,
    actor_id: str | None,
    run_id: str | None,
    thread_id: str,
    resume_value: Any,
) -> game_service.TurnResult:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        context = DmContext(
            db=db,
            user_id=user_id,
            actor_id=actor_id,
            run_id=run_id,
            turn_id=str(uuid.uuid4()),
        )
        return await game_service.resume(
            agent, thread_id=thread_id, context=context, resume_value=resume_value
        )


async def _play_session(
    *,
    user_id: str,
    run_id: str | None,
    actor_id: str | None,
    thread_id: str,
) -> None:
    async with checkpointer_service.checkpointer() as saver:
        agent = game_service.build_agent(checkpointer=saver)

        config = RunnableConfig(configurable={"thread_id": thread_id})
        state = await agent.aget_state(config)
        in_flight_interrupt = (
            state.tasks[0].interrupts[0].value
            if (state.tasks and state.tasks[0].interrupts)
            else None
        )

        while True:
            if in_flight_interrupt is not None:
                int_type = in_flight_interrupt.get("type")
                if int_type == "question":
                    q_text = in_flight_interrupt.get("text", "Choose an option:")
                    options = in_flight_interrupt.get("options", [])
                    typer.echo(f"\n[DM asks]: {q_text}")
                    for idx, opt in enumerate(options, 1):
                        typer.echo(f"  {idx}. {opt}")
                    try:
                        ans = await asyncio.to_thread(input, "?> ")
                    except (EOFError, KeyboardInterrupt):
                        break
                    ans_clean = ans.strip()
                    if ans_clean.isdigit():
                        idx = int(ans_clean) - 1
                        if 0 <= idx < len(options):
                            ans_clean = options[idx]
                    resume_val = ans_clean
                elif int_type == "roll_request":
                    req_kind = in_flight_interrupt.get("kind", "roll")
                    formula = in_flight_interrupt.get("formula", "")
                    typer.echo(f"\n[Roll Requested]: {req_kind} ({formula})")
                    try:
                        await asyncio.to_thread(input, "Press Enter to roll...")
                    except (EOFError, KeyboardInterrupt):
                        break
                    resume_val = {"action": "roll"}
                else:
                    try:
                        resume_val = await asyncio.to_thread(input, "?> ")
                    except (EOFError, KeyboardInterrupt):
                        break

                result = await _resume_turn(
                    agent,
                    user_id=user_id,
                    actor_id=actor_id,
                    run_id=run_id,
                    thread_id=thread_id,
                    resume_value=resume_val,
                )
            else:
                try:
                    player_text = await asyncio.to_thread(input, "> ")
                except (EOFError, KeyboardInterrupt):
                    break

                if not player_text.strip() or player_text.strip().lower() in (
                    ":quit",
                    ":q",
                    "exit",
                    "quit",
                ):
                    break

                result = await _run_turn(
                    agent,
                    user_id=user_id,
                    actor_id=actor_id,
                    run_id=run_id,
                    thread_id=thread_id,
                    text=player_text,
                )

            for roll in result.rolls:
                typer.echo(
                    f"rolled {roll['kind']} {roll['formula']}: {roll['faces']} "
                    f"{roll['modifier']:+d} = {roll['total']}",
                    err=True,
                )
            if result.reply:
                typer.echo(result.reply)

            in_flight_interrupt = result.interrupt


class _ToolAwareStubModel(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


@game_app.command("play")
def play(
    user_id: str = typer.Option(..., "--user", help="The caller's user id."),
    run_id: str | None = typer.Option(None, "--run-id", help="The campaign run id."),
    actor_id: str | None = typer.Option(
        None, "--actor", "--actor-id", help="Optional default actor id override."
    ),
    thread_id: str | None = typer.Option(None, "--thread-id", help="Checkpointer thread id."),
) -> None:
    active_thread_id = thread_id or str(uuid.uuid4())
    try:
        asyncio.run(
            _play_session(
                user_id=user_id,
                run_id=run_id,
                actor_id=actor_id,
                thread_id=active_thread_id,
            )
        )
    except (LlmError, PlaythroughError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


@game_app.command("graph")
def graph(
    output: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional file path to write the graph visualization (e.g. graph.png or graph.mmd).",
    ),
    format: str = typer.Option(
        "mermaid",
        "--format",
        "-f",
        help="Output format: 'mermaid' (default) or 'png'.",
    ),
) -> None:
    """Print or export the DM agent StateGraph visualization."""
    stub_model = _ToolAwareStubModel(messages=iter([]))
    agent = game_service.build_agent(model=stub_model)
    state_graph = agent.get_graph()

    fmt = format.lower()
    if output and output.lower().endswith(".png"):
        fmt = "png"

    if fmt == "png":
        try:
            png_bytes = state_graph.draw_mermaid_png()
        except Exception as exc:
            typer.echo(f"Failed to generate PNG: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        if output:
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(png_bytes)
            typer.echo(f"Saved graph image to {output}")
        else:
            sys.stdout.buffer.write(png_bytes)
    else:
        mermaid_code = state_graph.draw_mermaid()
        if output:
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(mermaid_code, encoding="utf-8")
            typer.echo(f"Saved mermaid diagram to {output}")
        else:
            typer.echo(mermaid_code)
