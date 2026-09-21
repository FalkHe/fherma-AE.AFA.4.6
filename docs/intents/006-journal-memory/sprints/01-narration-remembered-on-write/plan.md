---
author: sprint
owner: agent
created: 2026-09-21
---
# Plan: Sprint 01

Three surfaces in three different files — the events table, the one writer, one operator command — all parallel
against fixed interfaces. First sprint of intent 006.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | An event row can carry the meaning of its text and the name of what encoded it; past narration is indexed for a nearest-meaning search, everything else is not | AC1: both columns optional, surviving a write-then-read against a real database; the index covers narration with a vector only; nothing 0007 owns is touched | I1 |
| 2 | backend-python | Narration is encoded as it is written, its encoding billed onto that line, and a failure to encode never reaches the caller | AC2–AC4: narration stores vector and model name, tokens and cost on top of what the caller passed; every other kind stores nothing and never calls out; any failure — a wrong-width answer included — still writes the line, same return value, one warning logged | I2 |
| 3 | backend-python | An operator can write narration, or a player action, into a run from the command line and is told the new entry's id | AC5: both kinds append through the one writer and print the id; a refusal leaves the usual code on stderr and a non-zero exit | I3 |
| qa | qa | Black-box acceptance tests, one per criterion | below | I1–I3 |

## Interfaces
- **I1 — schema.** `playthrough/models.py`: `EMBEDDING_WIDTH = 1536`; `embedding: Mapped[list[float] | None] = mapped_column(VECTOR(EMBEDDING_WIDTH), nullable=True)`; `embedding_model: Mapped[str | None] = mapped_column(String, nullable=True)`. Index declared after the class, as `srd/models.py:36-41` does: `Index("ix_events_embedding_narration", Event.embedding, postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}, postgresql_where=text("type = 'narration' AND embedding IS NOT NULL"))`. Migration `alembic/versions/0008_event_embeddings.py`, `revision "0008"`, `down_revision "0007"`; `upgrade` = two `op.add_column` plus one `op.create_index`, same name, ops and `postgresql_where`; `downgrade` drops index then columns. No `CREATE EXTENSION` — `0002` owns it.
- **I2 — writer.** `append_event`'s signature and return value are unchanged. Before `Event(...)`, when `type == "narration"` and `validated.text.strip()` is non-empty: `result = await asyncio.to_thread(llm_service.embed_texts, [validated.text])` (module attribute, never a name import), `model_name = get_settings().embedding_model`. On success **and** `len(vector) == EMBEDDING_WIDTH`: set `event.embedding = vector`, `event.embedding_model = model_name`. On **any** `Exception`, or a wrong width: set neither and `logger.warning("narration_embedding_failed", run_id=run_id, error=str(exc))` — never re-raise. A wrong-width vector reaching the flush would abort the caller's transaction and lose the narration (← D4). Cost: `prompt_tokens` and `cost_usd` are the sum over the caller's `usage` and the embedding's, each skipped when absent, `None` when both are; `completion_tokens` stays the caller's value alone. Every non-`narration` type takes no branch: no call, no vector.
- **I3 — CLI.** `app playthrough narrate RUN_ID TEXT [--player-action]` — two `typer.Argument`s, one flag (default false), no `--user`: an operator command with no membership gate, like `app srd status`. Opens a session via `get_sessionmaker()`, calls `playthrough_service.append_event(db, run_id=RUN_ID, type="player_action" if flag else "narration", visibility="player", payload={"text": TEXT})`, `await db.commit()`, prints `event: {event.id}`. `PlaythroughError` → `f"{exc.code}: {exc}"` on stderr + `typer.Exit(1)`, as `cost` and `roll` do.

## Acceptance tests (qa)
`backend/tests/playthrough/test_acceptance_narration_remembered.py`. The suite pins the core embedding width to `4`, so a fake encoder must answer 1536 floats or nothing is ever stored.
- AC1 → `@pytest.mark.database`: write a narration row with a vector and read it back; the columns accept nothing; the index exists with its narration-only predicate.
- AC2 → narration stores vector and model name, and the encoding's tokens and cost are added to what the caller passed.
- AC3 → a player action, and one further kind, store no vector and trigger no call.
- AC4 → the encoder raising, and answering a wrong width: the line is still written with nothing stored, same return value, nothing propagates.
- AC5 → the command prints the new id for both kinds, and passes the flag through as the kind.

## Order
Parallel: WI1, WI2, WI3, qa.
