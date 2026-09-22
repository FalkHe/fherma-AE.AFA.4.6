---
author: fhit:architect
owner: agent
created: 2026-09-21
---
# Research: sprint 006/02 — recall by meaning, and a recap on return

## Facts

- **Read shape.** A playthrough read takes `(db, *, user_id, run_id, …)`, calls `_require_member`
  (`service.py:164`) first, and returns ORM rows (`list_events`, `service.py:2239-2268`) or a Pydantic model built
  from tuples (`run_cost`, `service.py:2320-2351`). No read commits; only `latest_event_id` rolls back
  (`service.py:2378`).
- **Unknown run.** `CampaignRunNotFoundError(run_id)`, `code = ErrorCode.NOT_FOUND` → HTTP 404
  (`errors.py:23-35`, `core/errors.py:39,80`), message `campaign run not found: {run_id}`. Raised by
  `_require_member` (`service.py:164-180`) and **`_get_run(db, run_id)` (`service.py:243-253`)** — a bare
  `select(CampaignRun).where(CampaignRun.id == run_id)`, the only existence check needing no `user_id`. That is
  where AC5's check belongs: in the service, first line of both functions, so the phase-8 DM tool layer inherits it
  and the CLI needs no new branch (its `except PlaythroughError` already prints `NOT_FOUND: …`). `_get_run`'s
  docstring ("once membership is already confirmed") must widen.
- **Cosine search.** No vector query exists yet: `srd` declares the index (`srd/models.py:36-41`) but
  `srd/service.py` only counts rows and reads the newest, so the operator is new here. pgvector 0.5.0
  (`backend/uv.lock:816`) — source: local, `pgvector/sqlalchemy/vector.py` `Comparator.cosine_distance` →
  `self.op('<=>', return_type=Float)`, taking a plain `list[float]`. Canonical shape
  `… WHERE <filters> ORDER BY embedding <=> $1 LIMIT k` — source: context7 `/pgvector/pgvector`. Our index is
  `ix_events_embedding_narration`, partial on `type = 'narration' AND embedding IS NOT NULL`
  (`playthrough/models.py:237-243`): the query's `WHERE` must repeat both predicates verbatim or Postgres cannot use
  it. The extra `campaign_run_id` filter costs recall on a filtered HNSW scan; `hnsw.iterative_scan` would fix that
  and stays unset — the planner seq-scans at this corpus size anyway.
- **Ordering and span.** `events.id` is a ULID and the transcript sorts by `id` alone; correct only because one
  process mints every id (`docs/modules/playthrough.md` §10, `playthrough/README.md:539-547`). Recency by `id` is
  therefore exactly as safe as the transcript read already is — no `created_at` tiebreak, no new caveat. `Event`
  carries `campaign_run_id` and no `adventure_run_id` (`models.py:190-235`), so that filter *is* the whole-run span
  (← D5).
- **CLI.** `playthrough_app = typer.Typer()` (`commands.py:70`), registered at `app/cli.py:41`. Each command wraps
  an `async def _helper()` opening `get_sessionmaker()`, runs it under `asyncio.run`, catches `PlaythroughError` →
  `typer.echo(f"{exc.code}: {exc}", err=True)` + `typer.Exit(code=1)`, then prints `f"label: value"` lines
  (`commands.py:161-189`). Tested with `CliRunner` against the real `app.cli.cli`, monkeypatching the **module
  attribute** `playthrough_service.<fn>` — engine-free, a lazy `AsyncEngine` opens no socket
  (`tests/playthrough/test_commands.py:1-95,143-208`).
- **Test seams.** `tests/conftest.py:25` pins `EMBEDDING_DIMENSIONS="4"` suite-wide and builds no engine.
  `scratch_db(**env_pins)` (`tests/database.py:127-152`) creates a scratch database, runs `alembic upgrade head`,
  pins `DATABASE_URL` plus each kwarg, restores all on teardown; `tests/srd/conftest.py:18` is the
  `EMBEDDING_DIMENSIONS="1536"` precedent, `tests/playthrough/conftest.py:13-14` pins nothing. Nothing in
  `playthrough` reads `embedding_dimensions` — only `llm/service.py:340` (the real `embed_texts`, monkeypatched in
  AC3) and `srd/service.py:15` — so the pin means consistency with the `VECTOR(1536)` column, not behaviour; the
  existing `database` tests are indifferent to it.
- **Stubbed session.** The default suite's `FakeSession` pops queued `FakeResult`s from `execute()`
  (`tests/playthrough/test_run_cost.py:34-59`, `test_service.py:65-105`); it never parses SQL. For AC4 it can prove
  the queued rows come back **reversed** into chronological order, their count, and that
  `service.llm_service.embed_texts` was never called — not `ORDER BY … DESC`, `LIMIT` or the `type` filter, real
  SQL that falls to AC3's `database` test. So `recap` must order in SQL (`id DESC LIMIT n`) and flip in Python, or
  AC4 is unprovable.

## Work items

- **WI1 — `recall` (fhit:backend-python)**: the semantic read, its `@pytest.mark.database` proof, and
  `playthrough_db` pinned to `EMBEDDING_DIMENSIONS="1536"`. (AC1, AC3)
- **WI2 — `recap` (fhit:backend-python)**: the recency read and its engine-free `FakeSession` proof. (AC2, AC4)
- **WI3 — CLI (fhit:backend-python)**: both commands, `CliRunner` tests monkeypatching the two service
  attributes. (AC5)

WI2 owns `NarrationRead` (I1); WI1 imports it. All three run in parallel against I1–I3.

## Interfaces

**I1 — result model** (`playthrough/schemas.py`, by WI2):
```python
class NarrationRead(CamelModel):
    id: str
    created_at: datetime
    text: str
```
Three fields, that order, for both functions — no distance, no payload, no vector. `EventRead` is not reused: it
is the transcript route's wire model and carries `type`/`turnId`/`payload`.

**I2 — service** (`playthrough/service.py`, after `latest_event_id`). Neither takes `user_id` — operator reads,
gated on existence alone — and both call `await _get_run(db, run_id)` as their **first** statement.

```python
async def recall(db: AsyncSession, *, run_id: str, query: str, k: int = 5) -> list[NarrationRead]
async def recap(db: AsyncSession, *, run_id: str, n: int = 5) -> list[NarrationRead]
```

`recall`: one embedding call, `result = await asyncio.to_thread(llm_service.embed_texts, [query])` — module
attribute, never a name import — then `vector = result.vectors[0]`; seam errors propagate unchanged (D4 covers
writes, not reads). Statement: `select(Event.id, Event.created_at, Event.payload).where(Event.campaign_run_id ==
run_id, Event.type == "narration", Event.embedding.is_not(None)).order_by(
Event.embedding.cosine_distance(vector)).limit(k)` — predicates matching the partial index verbatim; `Event`
itself is never selected, so no 1536-float vector crosses the wire. Rows map to
`NarrationRead(id=…, created_at=…, text=payload.get("text", ""))`, closest first, unfiltered by relevance.

`recap`: **no** embedding call. Same columns and mapping; `.where(Event.campaign_run_id == run_id, Event.type ==
"narration").order_by(Event.id.desc()).limit(n)`, then `list(reversed(rows))` — newest `n` chosen in SQL,
oldest-first on return. No `embedding IS NOT NULL` filter: recency does not care.

Both return `[]` when the run has no narration. Neither commits nor rolls back.

**I3 — CLI** (`playthrough/commands.py`, after `narrate`). Two commands, no `--user`:
`app playthrough recall RUN_ID QUERY [--k INTEGER]` (default 5) and `app playthrough recap RUN_ID [--n INTEGER]`
(default 5); `RUN_ID` and `QUERY` are `typer.Argument(...)`. Each opens its session as `_narrate` does, calls
`playthrough_service.recall(...)` / `.recap(...)`, and prints **one line per item, nothing else**:
`typer.echo(f"{item.id} {item.created_at.isoformat()} {item.text}")` — three fields, one space between, text last.
An empty result prints nothing and exits 0. `except PlaythroughError` → `f"{exc.code}: {exc}"` on stderr +
`typer.Exit(code=1)`: an unknown run prints `NOT_FOUND: campaign run not found: {RUN_ID}` and exits 1 (AC5).

## Open questions

- Product-visible: none. The defaults of 5 and the whole-run span are settled (brief Assumptions, ← D3, D5); when
  a resumed run gets its recap stays phase 8's.
- Technical, taken as assumptions unless overruled: `recall` lets an embedding failure surface rather than returning
  an empty list, so an operator is never shown "no memories" when the encoder is down; `playthrough_db` gains the
  `1536` pin rather than a second fixture; `hnsw.iterative_scan` stays unset; `_get_run` is reused rather than a new
  `_require_run` added.
