---
author: fhit:architect
owner: agent
created: 2026-09-21
---
# Research: sprint 006/01 — narration is remembered on write

## Facts

- `Event` (`playthrough/models.py:183-221`): `id, campaign_run_id, actor_member_id, turn_id, type, visibility,
  payload(JSONB), prompt_tokens, completion_tokens, cost_usd(Numeric(12,6)), created_at`; CHECK `type` over the twelve
  types incl. `narration` (`:196-201`), CHECK `visibility`, two composite indexes (`:203-204`). No vector column, no
  `updated_at`.
- Revision head is `0007` (`alembic/versions/0007_lifecycle_and_event_types.py:27-28`, `down_revision "0006"`); it
  landed with 005. `0008` is free.
- `vector` extension is already created by `0002_srd_rules.py:29`. SRD's precedent: `EMBEDDING_WIDTH = 1536`
  (`srd/models.py:13`), `VECTOR(EMBEDDING_WIDTH)` column (`:33`), `Index(..., postgresql_using="hnsw",
  postgresql_ops={"embedding": "vector_cosine_ops"})` declared outside the class (`srd/models.py:36-41`), mirrored in
  the migration (`0002_srd_rules.py:50-56`). Partial-index precedent in this module:
  `postgresql_where=text("status = 'active'")` (`playthrough/models.py:95`, `0004_adventure_runs.py:69`).
- `append_event` (`playthrough/service.py:2118-2186`) is the only writer of `events`, guarded by
  `tests/playthrough/test_only_event_writer.py`. It validates `payload` against `EVENT_PAYLOADS[type]`
  (`schemas.py:228`), builds `Event(...)` (`:2170`), copies `usage` into `prompt_tokens`/`completion_tokens`/
  `cost_usd` via `Decimal(str(...))` (`:2178-2182`), then `add` + `flush` — **no commit**; the caller owns the
  transaction.
- Narration payload field is `text` — `NarrationPayload` (`schemas.py:145-149`); `player_action` is
  `text` + `answers_question_id` (`:152-157`). `EventRead` on the wire carries only `id, type, turnId, payload,
  createdAt` (`schemas.py:31-42`), so new columns leak nowhere.
- `run_cost` sums `events.cost_usd` per turn (`service.py:2289-2294`), so embedding cost booked on the row is counted
  for free.
- Core seam: `embed_texts(texts: Sequence[str], *, model: str | None = None) -> EmbeddingResult`
  (`core/llm/service.py:350`); `EmbeddingResult = {vectors: list[list[float]], usage: Usage}` (`:88-91`);
  `Usage = {prompt_tokens, completion_tokens, total_tokens, cost_usd: float | None}` (`:80-85`). For embeddings
  `completion_tokens` is always `0` and `cost_usd` is the provider's cost (`:286-298`). **It does not report which
  model ran** — the caller resolves the name from `get_settings().embedding_model` (`core/settings.py:20`).
  It is **synchronous** and its retry sleeps with `time.sleep` (`core/llm/retry.py:39-42`, `:109`).
  It raises `LlmBadRequestError` on empty input and `LlmConfigurationError` when a returned vector's width differs
  from `EMBEDDING_DIMENSIONS` (`:340-345`).
- `playthrough/service.py` has **no logger** today; the structlog pattern is `logger = structlog.get_logger()`
  (`core/llm/service.py:74`).
- CLI: `playthrough_app = typer.Typer()` (`commands.py:54`), registered as
  `cli.add_typer(playthrough_app, name="playthrough")` (`app/cli.py:41`). Commands open their own session with
  `get_sessionmaker()` and `asyncio.run` (`commands.py:57-61`, `:81-89`), fail as `f"{exc.code}: {exc}"` to stderr
  plus `typer.Exit(1)`. Tested through `typer.testing.CliRunner` against the real `cli`, monkeypatching the service
  *module attribute* (`tests/playthrough/test_commands.py:1-45`).
- Tests: suite pins `EMBEDDING_DIMENSIONS = "4"` and builds no engine (`tests/conftest.py:19-27`);
  `filterwarnings = ["error"]`, marker `database` (`pyproject.toml:65-68`). Real database = `scratch_db(**env_pins)`
  (`tests/database.py:127`) behind the one-line `playthrough_db` fixture, currently pinned to nothing
  (`tests/playthrough/conftest.py:13-14`). Engine-free migration tests import the revision file and record `op` calls
  (`tests/playthrough/test_migration_0007.py`).
- pgvector 0.5.0 (`uv.lock:816-817`) — source: local package. `pgvector.sqlalchemy.VECTOR` binds and returns plain
  `list[float]` (`Vector._to_db` / `_from_db`), so the ORM round-trips without numpy and without any psycopg adapter
  registration. Source: context7 `/pgvector/pgvector` — a partial HNSW index (`... USING hnsw (...) WHERE (...)`) is
  supported, and NULL vectors are never indexed.

## Work items

- **WI1 — schema (fhit:backend-python)**: `EMBEDDING_WIDTH`, the two columns and the partial HNSW index in
  `playthrough/models.py`; migration `0008`; engine-free migration/model tests plus one `@pytest.mark.database`
  round-trip over `playthrough_db`. (AC1)
- **WI2 — writer (fhit:backend-python)**: the embedding path, cost accounting and failure handling in `append_event`;
  engine-free tests with `llm_service.embed_texts` monkeypatched. (AC2, AC3, AC4)
- **WI3 — CLI (fhit:backend-python)**: `app playthrough narrate`; `CliRunner` test monkeypatching
  `playthrough_service.append_event`. (AC5)

All three run in parallel against the interfaces below; WI2/WI3 never read WI1's file.

## Interfaces

**I1 — schema.** `playthrough/models.py`: `EMBEDDING_WIDTH = 1536`; `embedding: Mapped[list[float] | None] =
mapped_column(VECTOR(EMBEDDING_WIDTH), nullable=True)`; `embedding_model: Mapped[str | None] = mapped_column(String,
nullable=True)`. Index, declared after the class like SRD's:
`Index("ix_events_embedding_narration", Event.embedding, postgresql_using="hnsw",
postgresql_ops={"embedding": "vector_cosine_ops"}, postgresql_where=text("type = 'narration' AND embedding IS NOT
NULL"))`. Migration `alembic/versions/0008_event_embeddings.py`, `revision "0008"`, `down_revision "0007"`; `upgrade`
= two `op.add_column` + one `op.create_index` with the same name, ops and `postgresql_where`; `downgrade` drops index
then columns. No `CREATE EXTENSION` (0002 owns it), nothing else touched.

**I2 — writer.** `append_event`'s signature and return value are unchanged. Before `Event(...)`, when
`type == "narration"` and `validated.text.strip()` is non-empty:
`vectors, usage = await asyncio.to_thread(llm_service.embed_texts, [validated.text])` (module attribute, never a name
import) with `model_name = get_settings().embedding_model`. On success **and** `len(vector) == EMBEDDING_WIDTH`, set
`event.embedding = vector`, `event.embedding_model = model_name`. On **any** `Exception`, or a wrong width, set
neither and `logger.warning("narration_embedding_failed", run_id=run_id, error=str(exc))` — never re-raise (a
wrong-width vector must not reach the flush, where it would abort the caller's whole transaction). Cost: let
`sources = [u for u in (usage, embedding_usage) if u is not None]`; `prompt_tokens = sum(u.prompt_tokens …) or None`
when `sources` is empty, `completion_tokens` stays the caller's value only, `cost_usd = sum(Decimal(str(u.cost_usd))
…)` over sources with a non-`None` cost, else `None`. Every non-`narration` type takes no branch: no call, no vector.

**I3 — CLI.** `app playthrough narrate RUN_ID TEXT [--player-action]` — two `typer.Argument`s, one flag
(`--player-action`, default false) and no `--user` (operator command, no membership gate). Opens a session via
`get_sessionmaker()`, calls `playthrough_service.append_event(db, run_id=RUN_ID, type="player_action" if flag else
"narration", visibility="player", payload={"text": TEXT})`, then `await db.commit()`, and prints `event: {event.id}`.
`PlaythroughError` → `f"{exc.code}: {exc}"` on stderr + `typer.Exit(1)`, as `cost`/`roll` do.

## Open questions

- Product-visible: nothing in this sprint. D4 already rules that the player notices nothing when embedding fails;
  whether an operator ever learns how often it failed is Stage 02's backfill question.
- Technical, decided as assumptions unless overruled: blank narration text is stored with no vector and no warning
  (no call worth making); an unknown run id in `narrate` surfaces as the database's foreign-key error, not a formatted
  code, because `append_event` performs no lookup; `playthrough_db` keeps its no-pin form — the width guard compares
  against the module constant, never `EMBEDDING_DIMENSIONS`, so the suite-wide `4` stays harmless.
