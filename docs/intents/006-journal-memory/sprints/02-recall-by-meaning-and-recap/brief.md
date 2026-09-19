---
author: fhit:architect
owner: human
created: 2026-09-18
stage: approved
---
# Sprint 02: recall by meaning, and a recap on return

## Task
Add two reads to the playthrough service: one that embeds a query and returns the k narration events of a campaign run
closest in meaning, spanning every adventure in the run and skipping rows without a vector; and one that returns the
most recent N narration events of the run by recency alone, in chronological order. Expose the first as
`app playthrough recall <run-id> "<query>"` and the second as `app playthrough recap <run-id>`, both printing event
id, time and text.

## Outcome
Given a run with narration written in two different adventures, `app playthrough recall <run-id> "<phrase>"` prints
the semantically closest lines first — including the one from the earlier adventure — and never a line that failed to
embed, while `app playthrough recap <run-id>` prints the newest lines regardless of any query.

## Acceptance criteria
- AC1: `recall(db, *, run_id, query, k=5)` embeds `query` once through `embed_texts`, orders `narration` events of
  the whole campaign run by cosine distance to it and returns the closest `k` with id, time and text; rows with a null
  vector are excluded; no relevance floor (← D1, D5).
- AC2: `recap(db, *, run_id, n=5)` returns the `n` most recent `narration` events of the run by id, in chronological
  order, with no embedding call (← D3).
- AC3: Semantic ordering is proven by a `@pytest.mark.database` test over `scratch_db(EMBEDDING_DIMENSIONS="1536")`
  with `embed_texts` monkeypatched to fixed vectors: a query vector nearer A than B returns A first, and a row from an
  earlier adventure of the same run is returned when it is the closest (← D5).
- AC4: Recency is proven separately in the default suite against the stubbed session: `recap` returns the newest `n`
  in chronological order and makes no embedding call.
- AC5: `app playthrough recall <run-id> "<query>" [--k]` and `app playthrough recap <run-id> [--n]` print one line per
  event — id, time, text — and exit non-zero with a message when the run does not exist (`CliRunner`).

## Decisions
← D1, D3, D5

## Assumptions
- k = 5 and N = 5 as defaults, both overridable by a flag; the values are tuned in phase 8 once a DM runs.
- Both commands are operator commands with no membership gate, like `app srd search`; the `--user` gate stays on
  `app playthrough cost`, whose data is owner-only.
- The query embedding is not booked as an event: the recall is a read, and its cost is the DM turn's to record once
  phase 8 calls it.
- The search spans the campaign run, not one adventure run, by filtering on `campaign_run_id` alone (← D5).

## Out of scope
No DM tool registration or prompt rendering (phase 8) · no decision on when a resumed run gets its recap (← D3,
phase 8) · no relevance floor or tuning · no route or screen · no player-action search (← D2).
