"""Interactive CLI session against a real run. Reply on stdout, rolls on stderr.

Sprint 011/08, WI2: `_play_session` drives the new flow through
`game_service.run_turn` alone -- it never touches the compiled graph or a
checkpointer directly, exactly like the HTTP route. `run_turn` writes every
event; this module only reads them back (`playthrough_service.list_events`)
to render what just happened and to know what to prompt for next
(`TurnOutcome.awaiting`).
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import typer
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.runnables import RunnableConfig

from app.core.checkpointer import service as checkpointer_service
from app.core.db import get_sessionmaker
from app.core.ids import generate_id
from app.core.llm.errors import LlmError
from app.modules.game import service as game_service
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.errors import PlaythroughError
from app.modules.playthrough.models import Event
from app.modules.users import service as users_service

game_app = typer.Typer()

_QUIT_WORDS = (":quit", ":q", "exit", "quit")


def _print_turn_result(result: game_service.TurnResult) -> None:
    """Render narration and roll results with distinct terminal markers."""
    for roll in result.rolls:
        typer.echo(
            f"* rolled {roll['kind']} {roll['formula']}: {roll['faces']} "
            f"{roll['modifier']:+d} = {roll['total']}",
            err=True,
        )
    if result.reply:
        typer.echo(f"< {result.reply}")


def _turn_result_from_events(events: list[Event]) -> game_service.TurnResult:
    rolls = [
        {
            "kind": event.payload["kind"],
            "formula": event.payload["formula"],
            "faces": event.payload["faces"],
            "modifier": event.payload["modifier"],
            "total": event.payload["total"],
        }
        for event in events
        if event.type == "roll"
    ]
    narrations = [event.payload.get("text", "") for event in events if event.type == "narration"]
    return game_service.TurnResult(reply=narrations[-1] if narrations else "", rolls=rolls)


def _print_prompt_events(events: list[Event]) -> dict[str, Any] | None:
    """Echoes a pending `question`/`roll_requested` row exactly as the old
    session did, returning the `question` payload (for its `options`) when
    one was printed, or `None`."""
    pending_question: dict[str, Any] | None = None
    for event in events:
        if event.type == "question":
            pending_question = event.payload
            typer.echo(f"\n[DM asks]: {event.payload.get('text', 'Choose an option:')}")
            for idx, option in enumerate(event.payload.get("options", []), 1):
                typer.echo(f"  {idx}. {option}")
        elif event.type == "roll_requested":
            typer.echo(
                f"\n[Roll Requested]: {event.payload.get('kind', 'roll')} "
                f"({event.payload.get('formula', '')})"
            )
    return pending_question


async def _play_session(
    *,
    user_id: str,
    run_id: str | None,
    actor_id: str | None,
    thread_id: str,
) -> None:
    sessionmaker = get_sessionmaker()
    cursor: str | None = None
    pending_question: dict[str, Any] | None = None

    async def _do_turn(text: str | None) -> game_service.TurnOutcome:
        nonlocal cursor, pending_question
        async with sessionmaker() as db:
            outcome = await game_service.run_turn(db, user_id=user_id, run_id=run_id, text=text)
            events = await playthrough_service.list_events(
                db, user_id=user_id, run_id=run_id, after=cursor
            )
        if events:
            cursor = events[-1].id
        _print_turn_result(_turn_result_from_events(events))
        question = _print_prompt_events(events)
        if question is not None:
            pending_question = question
        return outcome

    outcome = await _do_turn(None)

    while True:
        if outcome.awaiting.startswith("roll:"):
            try:
                await asyncio.to_thread(input, "Press Enter to roll...")
            except (EOFError, KeyboardInterrupt):
                break
            outcome = await _do_turn(None)
            continue

        if outcome.awaiting.startswith("answer:"):
            try:
                answer = await asyncio.to_thread(input, "?> ")
            except (EOFError, KeyboardInterrupt):
                break
            answer_clean = answer.strip()
            options = (pending_question or {}).get("options", [])
            if answer_clean.isdigit():
                idx = int(answer_clean) - 1
                if 0 <= idx < len(options):
                    answer_clean = options[idx]
            outcome = await _do_turn(answer_clean)
            continue

        try:
            player_text = await asyncio.to_thread(input, "> ")
        except (EOFError, KeyboardInterrupt):
            break

        if not player_text.strip() or player_text.strip().lower() in _QUIT_WORDS:
            break

        outcome = await _do_turn(player_text)


class _ToolAwareStubModel(GenericFakeChatModel):
    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


async def _play(
    *,
    username: str,
    run_id: str | None,
    actor_id: str | None,
    thread_id: str,
) -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        user = await users_service.get_user_by_username(db, username=username)
    if user is None:
        raise typer.BadParameter(f"unknown username: {username}", param_hint="--user")

    user_id = user.id
    resolved_actor_id = actor_id
    if run_id is not None and actor_id is None:
        async with sessionmaker() as db:
            character = await playthrough_service.get_member_character(
                db, user_id=user_id, run_id=run_id
            )
            resolved_actor_id = character.id

    await _play_session(
        user_id=user_id,
        run_id=run_id,
        actor_id=resolved_actor_id,
        thread_id=thread_id,
    )


@game_app.command("play")
def play(
    username: str = typer.Option(..., "--user", help="The caller's username."),
    run_id: str | None = typer.Option(None, "--run-id", help="The campaign run id."),
    actor_id: str | None = typer.Option(
        None,
        "--actor",
        "--actor-id",
        help="Optional actor id override, skipping resolution from the run.",
    ),
    thread_id: str | None = typer.Option(
        None, "--thread-id", help="Checkpointer thread id override, defaults to the run id."
    ),
) -> None:
    active_thread_id = thread_id or run_id or generate_id()
    try:
        asyncio.run(
            _play(
                username=username,
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


def _jsonable(value: Any) -> Any:
    """Turn LangGraph snapshots and messages into ordinary JSON values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if model_dump is not None:
        return _jsonable(model_dump(mode="json"))
    attributes = getattr(value, "__dict__", None)
    if attributes is not None:
        return _jsonable(attributes)
    isoformat = getattr(value, "isoformat", None)
    if isoformat is not None:
        return isoformat()
    return str(value)


def _snapshot_id(snapshot: Any) -> str | None:
    config = getattr(snapshot, "config", {}) or {}
    configurable = config.get("configurable", {})
    checkpoint_id = configurable.get("checkpoint_id")
    return str(checkpoint_id) if checkpoint_id is not None else None


def _snapshot_json(snapshot: Any) -> dict[str, Any]:
    return {
        "checkpoint": _snapshot_id(snapshot),
        "created_at": _jsonable(getattr(snapshot, "created_at", None)),
        "metadata": _jsonable(getattr(snapshot, "metadata", {})),
        "next": _jsonable(getattr(snapshot, "next", ())),
        "values": _jsonable(getattr(snapshot, "values", {})),
        "tasks": _jsonable(getattr(snapshot, "tasks", ())),
        "config": _jsonable(getattr(snapshot, "config", {})),
        "parent_config": _jsonable(getattr(snapshot, "parent_config", None)),
    }


def _print_action_snapshot(snapshot: Any, *, verbose: bool) -> None:
    if verbose:
        typer.echo(json.dumps(_snapshot_json(snapshot), indent=2, default=str))
        return

    metadata = getattr(snapshot, "metadata", {}) or {}
    step = metadata.get("step", "?")
    source = metadata.get("source", "?")
    next_nodes = list(getattr(snapshot, "next", ()) or ())
    checkpoint = _snapshot_id(snapshot) or "?"
    created_at = getattr(snapshot, "created_at", None)
    when = f" {created_at}" if created_at else ""
    typer.echo(f"[{checkpoint}]{when} step={step} source={source} next={next_nodes or ['END']}")

    writes = metadata.get("writes")
    if writes:
        typer.echo(json.dumps(_jsonable(writes), indent=2, default=str))

    tasks = getattr(snapshot, "tasks", ()) or ()
    for task in tasks:
        task_name = getattr(task, "name", "?")
        interrupts = getattr(task, "interrupts", ()) or ()
        errors = getattr(task, "error", None)
        if interrupts:
            values = [getattr(item, "value", item) for item in interrupts]
            typer.echo(f"  task={task_name} interrupts={_jsonable(values)}")
        if errors:
            typer.echo(f"  task={task_name} error={errors}")


async def _actions_session(
    *,
    thread_id: str | None,
    follow: bool,
    verbose: bool,
    limit: int | None,
    poll_interval: float = 0.25,
) -> None:
    sessionmaker = get_sessionmaker()
    resolved_thread_id = thread_id
    if resolved_thread_id is None:
        async with sessionmaker() as db:
            resolved_thread_id = await playthrough_service.get_latest_campaign_run_id(db)
        if resolved_thread_id is None:
            typer.echo("No campaign runs found.", err=True)
            raise typer.Exit(code=1)

    async with checkpointer_service.checkpointer() as saver:
        agent = game_service.build_agent(
            model=_ToolAwareStubModel(messages=iter([])), checkpointer=saver
        )
        config = RunnableConfig(configurable={"thread_id": resolved_thread_id})
        history = agent.aget_state_history(config, limit=limit)
        snapshots = [snapshot async for snapshot in history]
        typer.echo(f"thread: {resolved_thread_id}")

        if not follow:
            for snapshot in reversed(snapshots):
                _print_action_snapshot(snapshot, verbose=verbose)
            return

        last_checkpoint = _snapshot_id(snapshots[0]) if snapshots else None
        try:
            while True:
                await asyncio.sleep(poll_interval)
                current = [
                    snapshot async for snapshot in agent.aget_state_history(config, limit=limit)
                ]
                new_snapshots = []
                for snapshot in current:
                    if _snapshot_id(snapshot) == last_checkpoint:
                        break
                    new_snapshots.append(snapshot)
                for snapshot in reversed(new_snapshots):
                    _print_action_snapshot(snapshot, verbose=verbose)
                if current:
                    last_checkpoint = _snapshot_id(current[0])
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass


@game_app.command("actions")
def actions(
    thread_id: str | None = typer.Argument(
        None, help="The LangGraph thread id (defaults to the latest campaign run)."
    ),
    follow: bool = typer.Option(
        False, "-f", "--follow", help="Only show new checkpoints and auto poll."
    ),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", help="Display complete checkpoint snapshots as JSON."
    ),
    limit: int | None = typer.Option(
        None, "--limit", min=1, help="Maximum number of checkpoints to inspect."
    ),
) -> None:
    """Inspect LangGraph checkpoints, node transitions, writes, and interrupts."""
    try:
        asyncio.run(
            _actions_session(thread_id=thread_id, follow=follow, verbose=verbose, limit=limit)
        )
    except (LlmError, PlaythroughError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


def _format_event(event: Event) -> str:
    payload = event.payload or {}
    ev_type = event.type
    visibility = event.visibility
    created = event.created_at.strftime("%H:%M:%S") if event.created_at else ""
    time_part = f"[{created}] " if created else ""

    if ev_type == "tool_call":
        name = payload.get("name", "")
        args = payload.get("args", {})
        result = payload.get("result")
        outcome = payload.get("outcome")
        details = f"{name}({args})"
        if outcome:
            details += f" -> {outcome}"
        elif result is not None:
            details += f" -> {result}"
        return f"{time_part}[TOOL:{visibility.upper()}] {details}"

    if ev_type == "roll":
        kind = payload.get("kind", "")
        formula = payload.get("formula", "")
        faces = payload.get("faces", [])
        modifier = payload.get("modifier", 0)
        total = payload.get("total", "")
        mod_str = f"{modifier:+d}" if isinstance(modifier, int) else str(modifier)
        details = f"{kind} {formula}: {faces} {mod_str} = {total}"
        return f"{time_part}[ROLL:{visibility.upper()}] {details}"

    if ev_type == "roll_requested":
        kind = payload.get("kind", "")
        actor = payload.get("actorId", "")
        formula = payload.get("formula", "")
        dc = payload.get("dc")
        dc_str = f" dc={dc}" if dc is not None else ""
        details = f"kind={kind} actor={actor} formula={formula}{dc_str}"
        return f"{time_part}[ROLL_REQ:{visibility.upper()}] {details}"

    if ev_type == "narration":
        text = payload.get("text", "")
        return f"{time_part}[NARRATION] {text}"

    if ev_type == "player_action":
        text = payload.get("text", "")
        return f"{time_part}[PLAYER] {text}"

    if ev_type == "question":
        text = payload.get("text", "")
        options = payload.get("options", [])
        opt_str = f" options={options}" if options else ""
        return f"{time_part}[QUESTION] {text}{opt_str}"

    if ev_type == "hp_changed":
        actor = payload.get("actorId", "")
        delta = payload.get("delta", 0)
        hp = payload.get("currentHp")
        max_hp = payload.get("maxHp")
        delta_str = f"{delta:+d}" if isinstance(delta, int) else str(delta)
        return f"{time_part}[HP] {actor} {delta_str} (hp: {hp}/{max_hp})"

    if ev_type == "item_moved":
        item = payload.get("itemId", "")
        from_loc = payload.get("from")
        to_loc = payload.get("to")
        return f"{time_part}[ITEM] {item} from={from_loc} to={to_loc}"

    if ev_type == "way_opened":
        way = payload.get("wayId", "")
        return f"{time_part}[WAY] opened: {way}"

    if ev_type == "rule_looked_up":
        query = payload.get("query", "")
        return f"{time_part}[RULE] {query}"

    if ev_type in ("adventure_started", "adventure_completed"):
        adv = payload.get("adventureId", "")
        return f"{time_part}[{ev_type.upper()}] {adv}"

    if ev_type == "scene_entered":
        scene = payload.get("sceneId", "")
        return f"{time_part}[SCENE] {scene}"

    if ev_type in ("system", "error", "warning"):
        msg = payload.get("message", payload)
        return f"{time_part}[{ev_type.upper()}] {msg}"

    return f"{time_part}[{ev_type.upper()}:{visibility.upper()}] {payload}"


def _event_json(event: Event) -> str:
    row = {
        "id": event.id,
        "campaign_run_id": event.campaign_run_id,
        "actor_member_id": event.actor_member_id,
        "turn_id": event.turn_id,
        "type": event.type,
        "visibility": event.visibility,
        "payload": event.payload,
        "prompt_tokens": event.prompt_tokens,
        "completion_tokens": event.completion_tokens,
        "cost_usd": str(event.cost_usd) if event.cost_usd is not None else None,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
    return json.dumps(row, indent=2, default=str)


def _print_event(event: Event, *, verbose: bool) -> None:
    if verbose:
        typer.echo(_event_json(event))
    else:
        typer.echo(_format_event(event))


async def _events_session(
    *,
    run_id: str | None,
    follow: bool,
    verbose: bool,
    poll_interval: float = 0.25,
) -> None:
    sessionmaker = get_sessionmaker()
    resolved_run_id = run_id
    if resolved_run_id is None:
        async with sessionmaker() as db:
            resolved_run_id = await playthrough_service.get_latest_campaign_run_id(db)
        if resolved_run_id is None:
            typer.echo("No campaign runs found.", err=True)
            raise typer.Exit(code=1)

    async with sessionmaker() as db:
        await playthrough_service.get_run(db, resolved_run_id)

    typer.echo(f"run: {resolved_run_id}")

    if not follow:
        async with sessionmaker() as db:
            events = await playthrough_service.list_all_events(db, run_id=resolved_run_id)
        for event in events:
            _print_event(event, verbose=verbose)
        return

    # Follow mode: -f => only new rows and auto poll
    async with sessionmaker() as db:
        last_event_id = await playthrough_service.get_latest_event_id(db, run_id=resolved_run_id)

    try:
        while True:
            await asyncio.sleep(poll_interval)
            async with sessionmaker() as db:
                events = await playthrough_service.list_all_events(
                    db, run_id=resolved_run_id, after_id=last_event_id
                )
            for event in events:
                _print_event(event, verbose=verbose)
                last_event_id = event.id
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass


@game_app.command("events")
def events(
    run_id: str | None = typer.Argument(
        None, help="The campaign run id (defaults to the latest run)."
    ),
    follow: bool = typer.Option(False, "-f", "--follow", help="Only show new rows and auto poll."),
    verbose: bool = typer.Option(
        False, "-v", "--verbose", help="Display the whole event row as JSON."
    ),
) -> None:
    """Stream or show all written event logs (including DM actions) for a campaign run."""
    try:
        asyncio.run(_events_session(run_id=run_id, follow=follow, verbose=verbose))
    except PlaythroughError as exc:
        typer.echo(f"{exc.code}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except KeyboardInterrupt:
        pass
