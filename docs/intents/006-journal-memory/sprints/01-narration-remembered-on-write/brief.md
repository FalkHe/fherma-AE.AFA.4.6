---
author: fhit:architect
owner: human
created: 2026-09-18
stage: approved
---
# Sprint 01: narration is remembered on write

## Task
Add a nullable embedding and its model name to the transcript's event rows, with a partial similarity index covering
narration only, in a standalone migration. Extend the transcript writer so a narration event is embedded before insert
and stored with its vector, and the embedding call's tokens and cost are added to that same event's cost columns;
every other event type is written untouched. If embedding fails for any reason, the narration is still written, with no
vector, and nothing changes for the caller.

## Outcome
With narration written into a run through `app playthrough narrate <run-id> "<text>"`, the event row carries a
1536-wide vector, its embedding model name and the embedding's tokens plus cost booked on that row; the same command
writing a player action stores no vector; and with the embedding seam made to raise, the narration row is still
written with a null vector and the command still reports success.

## Acceptance criteria
- AC1: Migration `0008` adds nullable `events.embedding VECTOR(1536)` and nullable `events.embedding_model`, plus a
  partial HNSW `vector_cosine_ops` index predicated on `type = 'narration' AND embedding IS NOT NULL`; it touches
  nothing `0007` changes and round-trips a read (`@pytest.mark.database`).
- AC2: `append_event` embeds the narration text through the core `embed_texts` seam before insert and stores vector
  and model name; the embedding usage is added to the event's `prompt_tokens` and `cost_usd` on top of whatever the
  caller passed (← D1, D2).
- AC3: A `player_action` (and every non-narration type) is written with `embedding IS NULL` and no embedding call
  is made (← D2).
- AC4: When `embed_texts` raises — any exception, classified or not — the narration row is still inserted with a
  null vector and null model name, the caller receives the same return value, and a `warning` is logged, not raised
  (← D4).
- AC5: `app playthrough narrate <run-id> "<text>" [--player-action]` appends the event through `append_event` and
  prints the new event id (`CliRunner`); no route is added.

## Decisions
← D1, D2, D4

## Assumptions
- `0008` chains on 005's `0007`; its content depends only on the events table as landed in `0006`, where `narration`
  is already an allowed type, so a late `0007` moves only the revision pointer.
- The vector width is the playthrough module's own constant, as the SRD module re-declares its own; nothing is
  promoted to `core/`.
- The narration text follows the field name of the payload model 005 sprint 05 defines.
- `narrate` is an operator command with no membership gate, like `app srd status`.
- The ORM vector type handles the round-trip; no raw SQL vector adapter is registered.

## Out of scope
No read or search (02) · no backfill of rows that failed to embed (← D4, Stage 02) · no DM tool, prompt or guard
(phase 8) · no route, screen or stream change (← D1) · `docs/roadmap/` untouched.
