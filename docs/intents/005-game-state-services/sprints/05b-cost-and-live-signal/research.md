---
author: fhit:architect
owner: agent
created: 2026-09-19
---
# Research: sprint 005/05 — the transcript records, filters and reports its cost

## Facts

**`events` after `0007`** (`playthrough/models.py:180`-`221`, `alembic/versions/0006_events.py:26`-`67`,
`0007_lifecycle_and_event_types.py:62`): `id` CHAR(26) PK (ULID, `core/ids.py:16`) · `campaign_run_id` FK
CASCADE · `actor_member_id` FK SET NULL, null · `turn_id` CHAR(26), null, no FK · `type` String(32) ·
`visibility` String(8) · `payload` JSONB **not null, no default** · `prompt_tokens`, `completion_tokens`
Integer, null · `cost_usd` `Numeric(12,6)` → `Decimal`, null · `created_at` timestamptz `now()`; no
`updated_at`, no unique constraint. CHECKs: `type` in the twelve (`narration player_action roll_requested roll question tool_call
scene_entered adventure_started adventure_completed system error warning`), `visibility` in `player|dm`.
Indexes: `ix_events_campaign_run_id_visibility_id` (`campaign_run_id, visibility, id`) — exactly the
`… visibility='player' AND id > :after ORDER BY id` read — and `ix_events_campaign_run_id_turn_id`.

**Payload shapes** (`decisions/mechanics.md` §"Shapes"): `roll_requested {kind, actor_id, formula, context}` ·
`roll {request_id?, kind, actor_id, formula, faces[], modifier, total}` · `tool_call {name, args, roll_ids[],
result: ok|refused, outcome{}}` · `question {text, options[]}` · `player_action {text, answers_question_id?}` ·
`scene_entered {adventure_run_id, scene_id}` · `adventure_started`/`adventure_completed {adventure_run_id}`.
`narration`, `system`, `error`, `warning` have none — see Open questions.

**Module today.** Gate `_require_member` first in every function, one query, unknown *and* foreign →
`CampaignRunNotFoundError` (`service.py:114`-`129`, ← D12); the service commits (`:163`). Thin route wrapped in
`except PlaythroughError as exc: raise ApiError(exc.code) from exc` (`routes.py:35`), mounted at
`/api/v1/playthrough` (`api/v1/router.py:12`); `CurrentAuth` = session cookie (`auth/dependencies.py:37`). Wire
= `CamelModel`, storage = `BaseModel`, one error class per failure with `code: ErrorCode`
(`core/schemas.py:7`, `schemas.py:40`, `errors.py:13`-`31`).

**CLI.** One `typer.Typer()` per module in `commands.py`, added in `app/cli.py:30`-`34`; with no request scope
it opens its own session via `get_sessionmaker()` inside `asyncio.run(...)` and fails with one stderr line +
`typer.Exit(1)` (`srd/commands.py:34`-`50`). `CliRunner` drives the real `cli` with the service module attribute
monkeypatched; the lazy engine never connects (`tests/srd/test_commands.py:1`-`43`). **Settings**: an annotated
field with a default, `Field(...)` for bounds (`core/settings.py:18`-`21`), cached — tests `setenv` +
`get_settings.cache_clear()` in **and out** (`tests/conftest.py:101`-`116`).

**Nothing streams yet** — no `StreamingResponse` or `text/event-stream` anywhere. starlette **1.6.0**
`TestClient` buffers (whole app inside `portal.call(...)`, `testclient.py:349`-`365`) and withholds
`http.disconnect` until the response completes (`:299`-`305`): `client.stream` returns only **after** the
generator ends, and disconnect is unobservable through it. `Request.is_disconnected()` is non-blocking there and
returns `False` (`requests.py:328`-`340`). uvicorn **0.52.4** sends spec_version `2.3` (`h11_impl.py:207`), so
starlette also cancels the body task on a real disconnect (`responses.py:272`-`280`). (Versions: local
site-packages.)

**Id ordering (§C2).** `ULID()` goes through one module-level generator holding a `threading.Lock` and a
`StrictMonotonicPolicy` that increments the random part within a millisecond
(`ulid/__init__.py:117`,`:164`-`240`): strictly increasing **per process**. Another process minting in the same
millisecond would interleave; the API is one uvicorn process, no `--workers` (`docker/entrypoint-web.sh:10`).
`created_at` is `now()` = transaction start, so rows from one transaction share it and cannot break a tie
(`tests/playthrough/test_acceptance_event_stream.py:22`-`29`). Hence `ORDER BY id` alone; `after=` skips an
event only if two transactions on *one* run commit out of id order — impossible today (one player, one
request-scoped transaction per write). The fix would be a per-run sequence column; nothing needs it yet.

## Work items

- **WI1 the single writer + payload models** (AC1), with the guard test that nothing else writes `events`.
  **Sequential, first** — the registry is WI2/WI4's vocabulary.
- **WI2 the events read** (AC2): member-gated, ordered, `player`-only, plus the real-database test that a `dm`
  event between two `player` events is missing from the response and present in the table.
- **WI3 cost** (AC3): the gated per-run and per-turn sum, the CLI one-off, its registration, and the test that
  no HTTP route exposes cost.
- **WI4 the SSE signal** (AC4): two settings and the polled `updated` signal behind the same gate.
- **WI5 documentation**: `docs/modules/playthrough.md` §7/§8 and the README. **Sequential, last**.

WI2 ‖ WI3 ‖ WI4 after WI1; WI2 and WI4 both append to `routes.py` and `service.py`, so merge WI2 first.

## Interfaces

**`append_event(db, *, run_id, type, visibility, payload, turn_id=None, actor_member_id=None, usage=None)
-> Event`** — async, `add` + `flush` so the id exists, no commit (the caller owns the transaction). `payload`, a
dict or the type's model, is validated through `EVENT_PAYLOADS[type]` and stored `model_dump(by_alias=True)`;
an unknown `type`/`visibility` or a failing payload raises `InvalidEventPayloadError` (new,
`ErrorCode.VALIDATION_ERROR`) and is never written. `usage` is `core.llm.service.Usage`: tokens copy across,
`cost_usd` becomes `Decimal(str(usage.cost_usd))`, never `Decimal(float)` — it is `float | None` there
(`core/llm/service.py:70`-`74`) and AC3 needs exact decimals. No membership check; callers are gated.

**Payload models** (`schemas.py`, `CamelModel`, `extra="forbid"`), registry `EVENT_PAYLOADS: dict[str,
type[BaseModel]]` over all twelve: `NarrationPayload`, `PlayerActionPayload`, `RollRequestedPayload`,
`RollPayload`, `QuestionPayload`, `ToolCallPayload`, `SceneEnteredPayload`, `AdventurePayload` (both adventure
types), `NoticePayload` (`system`/`error`/`warning`).

**Read.** `GET /api/v1/playthrough/campaign/{run_id}/events?after=<id>&limit=<n>` → `list[EventRead]`,
`CurrentAuth`, `404 NOT_FOUND` for unknown/foreign. `after` optional, 26 chars, exclusive; `limit`
`Query(default=200, ge=1, le=500)`. `list_events(db, *, user_id, run_id, after=None, limit=200) -> list[Event]`,
`visibility='player'`, `ORDER BY id`. `EventRead` (`CamelModel`): `id, type, turnId, payload, createdAt` — no
`visibility` (always `player`), no cost, no `campaignRunId`.

**Stream.** `GET …/campaign/{run_id}/stream`, `CurrentAuth`; membership checked **before** the
`StreamingResponse` is returned, so refusal is still an envelope. `media_type="text/event-stream"`,
headers `cache-control: no-cache`, `x-accel-buffering: no`. Per tick `data: {"type":"updated","id":"<ulid>"}\n\n`
when `latest_event_id(db, *, user_id, run_id) -> str | None` differs from the last sent, else keepalive
`: keepalive\n\n`. Settings `sse_poll_interval_seconds: float = Field(default=2.0, gt=0)`,
`sse_max_lifetime_seconds: float = Field(default=300.0, gt=0)`, read by `get_settings()` **inside the handler**.
The loop ends on `await request.is_disconnected()`, elapsed lifetime or `GeneratorExit`, and rolls back per
poll so an open stream never sits idle-in-transaction.

**Cost.** `run_cost(db, *, user_id, run_id) -> RunCost`; `RunCost(total: Decimal, turns: list[TurnCost])`,
`TurnCost(turn_id: str | None, total: Decimal)` (plain `BaseModel`, no route), turns by `turn_id`, `NULL` last,
empty sums normalised to `Decimal("0.000000")`. `app playthrough cost <RUN_ID> --user <USER_ID>` (both
required) prints, exit 0:

```
run: <run-id>
total: 0.001234
turn <turn-id>: 0.000500
turn -: 0.000734
```

`PlaythroughError` → `f"{exc.code}: {exc}"` on stderr + `typer.Exit(1)`, so a foreign run prints `NOT_FOUND`.

**Tests.** SSE: pin both settings tiny (0.01/0.05) from a cache-clearing fixture, fake `latest_event_id`;
`client.stream(...)` then returns at lifetime end. Prove disconnect off-ASGI: one `asyncio.run(...)` over the
generator with a request disconnecting on the second call, then `await gen.aclose()` (unclosed generators warn;
warnings are errors). Only writer: `ast`-parse `backend/app`, assert `Event(` occurs in one function. D14: no
`/playthrough` path or OpenAPI entry carries `cost`; `GET …/cost` answers `NOT_FOUND`.

## Open questions

All agent-level, each called here; none product-visible.

- The four undeclared shapes: `narration {text}`, `NoticePayload {message, details?}` for
  `system`/`error`/`warning`.
- `payload` is stored camelCase (`CamelModel`, `by_alias=True`), so the read passes it through unmapped;
  sprint 07 reads `payload["actorId"]`.
- 300 s lifetime: `EventSource` reconnects itself, so the cut is invisible.
