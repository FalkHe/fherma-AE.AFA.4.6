---
author: sprint
owner: agent
created: 2026-09-16
---
# Plan: Sprint 03 — the corpus is ingested

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The stored rules become a searchable corpus: every passage is turned into a vector and written, and a run that fails part-way leaves no rows at all rather than half a rulebook. | chunk order preserved into rows; each row carries version, heading path, ordinal, text, token count, model and a full-width vector; no batch exceeds the request cap; the report sums tokens and known costs; a failing batch leaves zero rows and re-raises the gateway error untouched; a width mismatch raises before any call | I1 |
| 2 | backend-python | An operator can import the rules for real and watch it happen: the run reports progress, then what it did and what it cost; a gateway failure is one plain line, not a crash. | report shows version, bytes, passages, tokens, cost; one progress line per batch; a gateway error gives one stderr line and exit 1, no traceback; `--dry-run` behaviour unchanged | I1, I2 |
| 3 | backend-python | The project's description of the rules component matches what it now does. | module README names the landed import and its cost line; the architecture line saying import is still to come is current | – |
| qa | qa | Black-box acceptance tests, one per criterion. | below | I1, I2 |

## Interfaces
- **I1** — in `backend/app/modules/srd/service.py`: `EMBED_BATCH_SIZE = 256`; `async def ingest(db: AsyncSession, *, version: str = SOURCE_VERSION, on_batch: Callable[[int, int], None] | None = None) -> IngestReport`. `on_batch(chunks_done, chunks_total)` fires after each batch; the service never prints. `ingest` calls `llm_service.embed_texts(...)` attribute-style and lets `LlmError` travel out unwrapped, so the command can name the gateway's own code.
- **I2** — `backend/app/modules/srd/commands.py`: the existing `@srd_app.command("ingest")` gains its non-dry path; it catches `LlmError` and `SrdError` only.

## Decided here
- AC4 means the **promise**, not the mechanism: a failed run leaves the corpus empty rather than half-filled. All vectors are obtained first, then written in one short transaction — holding one transaction across the gateway calls pins a connection for a minute and buys nothing.
- The run prints one progress line per batch. A silent minute is worse for the operator than nine lines.
- A run where the gateway prices only some batches reports the sum it does know, labelled as incomplete, rather than hiding the figure entirely.

## Acceptance tests (qa)
- AC1 → the real import completes and prints source version, bytes, passage count, token count and USD cost.
- AC2 → asking for the corpus's state straight afterwards reports a non-zero passage count, the model used and the import time, and exits 0 where it exited 1 before.
- AC3 → every row carries heading path, ordinal, text, token count and model, and its vector is the configured width.
- AC4 → a gateway failure part-way through leaves no rows behind and surfaces as the gateway's own error code.
- AC5 → nothing outside the rules module reads or writes the corpus table; the command line is the only way in.

## Order
Parallel: WI1, WI3, qa. Then WI2. Then the live import, run by the sprint lead.
