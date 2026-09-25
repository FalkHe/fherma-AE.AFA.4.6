"""`app playthrough cost` -- sprint 005/05b WI1, binding interface in
`docs/intents/005-game-state-services/sprints/05b-cost-and-live-signal/plan.md`
(I2).

Thin CLI over `playthrough/service.py`'s `run_cost` (WI1). The command opens
its own DB session via `app.core.db.get_sessionmaker` -- the same helper
FastAPI's `get_db_session` wraps -- exactly the way `srd/commands.py`'s
`status` command does it, because there is no request scope to hang a
`Depends(...)` off in a Typer command.

This is cost's *only* address (← D14): no HTTP route ever exposes it.
Failure is `f"{exc.code}: {exc}"` to stderr plus `typer.Exit(code=1)`, per
`modules/srd/commands.py` -- a foreign or unknown run prints `NOT_FOUND`.

`app playthrough roll` -- sprint 005/07a WI4, binding interface in
`docs/intents/005-game-state-services/sprints/07a-rolls-derived-and-recorded/
plan.md` (I3), command half of AC4a.

Rolling has no HTTP route either, for the same reason `use_exit` has none
(← D14): the only intended caller of `service.roll` is the Dungeon
Master's own tool layer, a later phase's work. Until that exists, this
command exercises the same derivation and roll from the terminal --
`service.roll` does both the request and the answer at once, so the one
returned `roll` event carries everything worth showing: kind, actor,
formula, dice, modifier and total. It opens its session the same way
`cost` does -- there is no second way in this module.

`context` is built from whichever of `--ability`, `--item`, `--attack` and
`--expression` the caller gave; `derive_formula` (`dice.py`) decides which
keys a given `kind` actually reads -- this command adds no flag beyond
those four, so there is no way to hand a `custom` roll's expression to any
other kind (← D6, I4).

Failure is exactly `cost`'s shape: `f"{exc.code}: {exc}"` to stderr plus
`typer.Exit(code=1)`. A malformed `custom` expression raises
`dice.InvalidDiceExpressionError`, not a `PlaythroughError` -- a different
base class, but the same `.code`/message shape -- so it is caught
alongside `PlaythroughError` and let through unreformatted, naming the
expression exactly as `dice.py` already does.

`app playthrough narrate` -- sprint 006/01 WI3, binding interface in that
sprint's `plan.md` (I3), command half of AC5.

An operator command with no membership gate, like `app srd status`: no
`--user`, `append_event` performs no run lookup of its own. Writes one
`narration` or, with `--player-action`, one `player_action` event --
always `visibility="player"`, always `payload={"text": <TEXT>}` -- through
`service.append_event`, the module's one writer, then commits and prints
the new event's id. Opens its session the same way `cost` and `roll` do.
An unknown run id is not a `PlaythroughError` here (`append_event` does no
lookup): it surfaces as the database's own foreign-key error, accepted for
this sprint. A refusal that *is* a `PlaythroughError` -- an unrecognised
event type or visibility, neither reachable through this command's fixed
arguments today -- fails exactly like `cost` and `roll`: `f"{exc.code}:
{exc}"` to stderr plus `typer.Exit(code=1)`.

`app playthrough recall` and `app playthrough recap` -- sprint 006/02 WI3,
binding interface in
`docs/intents/006-journal-memory/sprints/02-recall-by-meaning-and-recap/
plan.md` (I3), command half of AC5.

Both are operator commands with no membership gate, exactly like `narrate`:
no `--user`. Each opens its session the same way, calls the like-named
`playthrough_service` function -- `recall(db, run_id=..., query=...,
k=...)` or `recap(db, run_id=..., n=...)` -- and prints one line per
returned item: `f"{item.id} {item.created_at.isoformat()} {item.text}"`,
nothing else. An empty result prints nothing and exits `0`. The run lookup
lives in the service, not here, so a foreign or unknown run surfaces as
`CampaignRunNotFoundError` and fails exactly like every other command in
this module: `f"{exc.code}: {exc}"` to stderr plus `typer.Exit(code=1)`.
"""

import asyncio
import json
from typing import Any

import typer

from app.core.db import get_sessionmaker
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.dice import InvalidDiceExpressionError
from app.modules.playthrough.errors import PlaythroughError
from app.modules.playthrough.models import Event
from app.modules.playthrough.schemas import RollKind, RunCost

playthrough_app = typer.Typer()


async def _fetch_cost(*, run_id: str, user_id: str) -> RunCost:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        return await playthrough_service.run_cost(db, user_id=user_id, run_id=run_id)


@playthrough_app.command("cost")
def cost(
    run_id: str = typer.Argument(..., help="The campaign run id."),
    user_id: str = typer.Option(..., "--user", help="The caller's user id."),
) -> None:
    try:
        result = asyncio.run(_fetch_cost(run_id=run_id, user_id=user_id))
    except PlaythroughError as exc:
        typer.echo(f"{exc.code}: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"run: {run_id}")
    typer.echo(f"total: {result.total:.6f}")
    for turn in result.turns:
        label = turn.turn_id if turn.turn_id is not None else "-"
        typer.echo(f"turn {label}: {turn.total:.6f}")


async def _run_roll(
    *, actor_id: str, user_id: str, kind: RollKind, context: dict[str, Any]
) -> Event:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        return await playthrough_service.roll(
            db, user_id=user_id, actor_id=actor_id, kind=kind, context=context
        )


@playthrough_app.command("roll")
def roll(
    # ruff's B008 fires on this one `typer.Argument(...)` call, and only
    # this one, purely because `RollKind` is a `Literal` alias rather than
    # a builtin scalar type -- it does not resolve type aliases before
    # deciding a default call is exempt. Every other call below is the
    # same shape and stays unflagged; this is the narrowest suppression.
    kind: RollKind = typer.Argument(  # noqa: B008
        ..., help="The kind of roll to derive and make."
    ),
    actor_id: str = typer.Option(..., "--actor", help="The rolling actor's object id."),
    user_id: str = typer.Option(..., "--user", help="The caller's user id."),
    ability: str | None = typer.Option(
        None, "--ability", help="The ability an 'ability_check' or 'saving_throw' names."
    ),
    item_id: str | None = typer.Option(
        None, "--item", help="The item template an 'attack'/'damage' comes from."
    ),
    attack: str | None = typer.Option(
        None,
        "--attack",
        help="Which of the actor's or item's attacks, when there is more than one.",
    ),
    expression: str | None = typer.Option(
        None, "--expression", help="The 'NdM+-K' expression a 'custom' roll uses verbatim."
    ),
) -> None:
    context: dict[str, Any] = {}
    if ability is not None:
        context["ability"] = ability
    if item_id is not None:
        context["item_id"] = item_id
    if attack is not None:
        context["attack"] = attack
    if expression is not None:
        context["expression"] = expression

    try:
        event = asyncio.run(
            _run_roll(actor_id=actor_id, user_id=user_id, kind=kind, context=context)
        )
    except (PlaythroughError, InvalidDiceExpressionError) as exc:
        typer.echo(f"{exc.code}: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    payload = event.payload
    typer.echo(f"kind: {payload['kind']}")
    typer.echo(f"actor: {payload['actorId']}")
    typer.echo(f"formula: {payload['formula']}")
    typer.echo(f"dice: {payload['faces']}")
    typer.echo(f"modifier: {payload['modifier']}")
    typer.echo(f"total: {payload['total']}")


async def _narrate(*, run_id: str, text: str, player_action: bool) -> Event:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        event = await playthrough_service.append_event(
            db,
            run_id=run_id,
            type="player_action" if player_action else "narration",
            visibility="player",
            payload={"text": text},
        )
        await db.commit()
        return event


@playthrough_app.command("narrate")
def narrate(
    run_id: str = typer.Argument(..., help="The campaign run id."),
    text: str = typer.Argument(..., help="The narration or player action text."),
    player_action: bool = typer.Option(
        False, "--player-action", help="Write a 'player_action' event instead of 'narration'."
    ),
) -> None:
    try:
        event = asyncio.run(_narrate(run_id=run_id, text=text, player_action=player_action))
    except PlaythroughError as exc:
        typer.echo(f"{exc.code}: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"event: {event.id}")


async def _recall(*, run_id: str, query: str, k: int) -> list[Any]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        return await playthrough_service.recall(db, run_id=run_id, query=query, k=k)


@playthrough_app.command("recall")
def recall(
    run_id: str = typer.Argument(..., help="The campaign run id."),
    query: str = typer.Argument(
        ..., help="Free-form text to find remembered narration by meaning."
    ),
    k: int = typer.Option(5, "--k", help="Maximum number of remembered entries to return."),
) -> None:
    try:
        items = asyncio.run(_recall(run_id=run_id, query=query, k=k))
    except PlaythroughError as exc:
        typer.echo(f"{exc.code}: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    for item in items:
        typer.echo(f"{item.id} {item.created_at.isoformat()} {item.text}")


async def _recap(*, run_id: str, n: int) -> list[Any]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as db:
        return await playthrough_service.recap(db, run_id=run_id, n=n)


@playthrough_app.command("recap")
def recap(
    run_id: str = typer.Argument(..., help="The campaign run id."),
    n: int = typer.Option(5, "--n", help="Number of most recent remembered entries to return."),
) -> None:
    try:
        items = asyncio.run(_recap(run_id=run_id, n=n))
    except PlaythroughError as exc:
        typer.echo(f"{exc.code}: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    for item in items:
        typer.echo(f"{item.id} {item.created_at.isoformat()} {item.text}")


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


@playthrough_app.command("events")
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
