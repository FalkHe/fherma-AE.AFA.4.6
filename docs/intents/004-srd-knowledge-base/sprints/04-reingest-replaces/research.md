---
author: fhit:architect
owner: agent
created: 2026-09-16
---
# Research: sprint 004/04 — a second ingest replaces the corpus

## Facts

Replacement already exists. `ingest` embeds every chunk first, then opens one short
transaction — `delete(SrdRule)`, `add_all(rows)`, `commit`, `rollback` on any exception
(`backend/app/modules/srd/service.py:352-358`). Nothing is written until every vector is in
hand (`service.py:322-333`), so a gateway failure never reaches the database at all.
`created_at` is `server_default=func.now()` (`models.py:33`) — transaction start time, so
every row of one run shares one timestamp, and `corpus_status` reports the newest
(`service.py:52-58`). Verified on the live dev corpus: 2,132 rows, `min(created_at) ==
max(created_at)`.

**AC1 — already true, unproven.** Same source ⇒ same chunk count ⇒ same row count; each run
is a new transaction, so `now()` is strictly later. No test runs ingest twice and then
`status`.

**AC2 — holds today by luck, not by construction.** The table has no uniqueness beyond the
`id` primary key (`models.py:25-33`, `alembic/versions/0002_srd_rules.py:47`). Uniqueness
rests entirely on the chunker: ordinals restart at 0 per section (`service.py:201-232`), so
two sections sharing a `heading_path` both emit ordinal 0. Anchor stripping
(`service.py:169-172`) can cause exactly that collision; demonstrated with two sibling
headings differing only by `{#fire-bolt}` / `{#fire-bolt-1}`, which produced the duplicate
pair `("Spells › Fire Bolt", 0)`. On the real source it does not happen: 2,098 headings, 124
anchors, 2,026 bodied sections, **zero** colliding paths, 2,132 chunks, zero duplicate pairs
— and zero duplicates in the live database. One upstream edit adding a repeated heading
silently breaks AC2. **Needs work.**

**AC3 — already true, unproven for a *loaded* corpus.** The committed failure test starts
from an empty corpus and asserts zero rows after
(`backend/tests/srd/test_ingest_service.py:286`, `test_acceptance_corpus_ingested.py:225`).
Nothing asserts that a pre-loaded corpus keeps its count *and* its ingest time.

**AC4 — the successful half is expressible; the "never disagree" half is not.** A locally
edited stored file cannot be re-ingested: `ingest` calls `fetch_source` first, which
overwrites the file before `chunk_source` reads it (`service.py:311-312`, `70-130`). AC4 must
therefore be exercised through the network seam — a changed upstream body — as
`test_acceptance_fetch_and_chunk.py:107` already does for the file alone; the database half is
untested. The real gap: `fetch_source` succeeds and overwrites the file, then embedding
fails, so the working tree carries a new source while the corpus still holds the old one —
the one state AC4 forbids, produced by the very scenario AC3 blesses. **Needs a decision.**

**AC5 — already true, unproven.** One transaction (above); Postgres MVCC means a reader on
another connection sees the old corpus or the new one, never a partial one. No test states it.

## Work items

- **WI1 (tests only)**: new `backend/tests/srd/test_acceptance_reingest_replaces.py` — a
  second ingest keeps the count and moves the ingest time later (AC1); a gateway failure on a
  later batch over an already-loaded corpus leaves count *and* ingest time untouched (AC3); a
  changed upstream body changes stored bytes and row count together in one run (AC4); the
  write is one transaction — delete, insert and a single commit, with a reader on a second
  connection never seeing a count other than the old or the new (AC5).
- **WI2 (code + tests)**: make the pair unique by construction — `chunk_source` numbers
  ordinals per `heading_path` rather than per section, so a collided path continues the
  numbering instead of restarting — and enforce it in the store with a unique constraint on
  `(source_version, heading_path, ordinal)` in a new `0003` migration. Output for today's
  source is unchanged (no collisions exist), and a future collision fails the ingest loudly
  inside the transaction, leaving the old corpus intact, instead of duplicating silently
  (AC2).

Most of this sprint is proving behaviour that sprint 03 already built; only AC2 is new code.

## Interfaces

WI2 changes one contract WI1 must not contradict:

> `chunk_source(path) -> list[RuleChunk]`: `ordinal` is the passage's position, from 0,
> among **all** passages sharing its `heading_path` in the document — not within one section.
> `(heading_path, ordinal)` is unique across the returned list.

## Open questions

**Product-visible** — a run that fetches a changed source and then fails while embedding
leaves the repository showing a new source and the corpus still serving the old rules. Should
a failed ingest restore the previous source file, so the two can never disagree, or is it
enough that the operator sees the failure and re-runs before committing?

**Internal** — the unique constraint is belt-and-braces once ordinals are unique by
construction; keeping both costs one small migration and makes AC2 a property of the store
rather than of the chunker. Assumed worth it.
