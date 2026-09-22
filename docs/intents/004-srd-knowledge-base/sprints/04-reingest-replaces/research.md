---
author: fhit:architect
owner: agent
created: 2026-09-22
---
# Research — 004/04 re-ingest replaces

## Facts

Production code already implements every criterion; sprint 03 shipped it. What is missing is proof.

- Ingest order: width check, remember previous source bytes, fetch, chunk, embed **all** batches, then one
  `delete(SrdRule)` + `add_all` + `commit` with `rollback` on failure and source restore on any failure —
  `backend/app/modules/srd/service.py:334-388`.
- AC1 (same count, later time): the delete/insert pair rewrites every row, `created_at` defaults to
  `now()` server-side (`backend/app/modules/srd/models.py:33`), and `corpus_status` reports the newest row
  (`service.py:69-75`). **Satisfied, no test of a second run.** Live: 1750 rows, ingested 10:09 UTC today.
- AC2 (no passage twice): `UniqueConstraint(source_version, heading_path, ordinal)`
  (`models.py:35`, `backend/alembic/versions/0009_srd_rules_unique_citation.py:21`), present on the live
  table. Live check: 1750 rows / 1750 distinct `(heading_path, ordinal)`. The stored source yields 1664
  heading sections with **zero** duplicate heading paths, so per-section `ordinal` (`service.py:252`) is
  globally unique for this source. **Satisfied, no test.** Risk worth a line in the sprint: a future source
  with two identical heading paths would violate the constraint at commit — the ingest would fail loudly and
  leave the old corpus intact (fail-safe), but it would never succeed until chunking disambiguates.
- AC3 (failure after some batches embedded): the write block is not entered until the embed loop finished
  (`service.py:352-382`), so no row is touched. The existing test
  `test_ingest_on_embedding_failure_adds_and_commits_nothing_and_restores_the_source`
  (`backend/tests/srd/test_ingest_service.py:105`) fails on the **first and only** batch — it does not prove
  the "after some batches" case. **Satisfied, proof incomplete.**
- AC4 (row count follows the stored file): `chunk_source` is a pure function of the file bytes
  (`service.py:233-261`; `count_tokens` is deterministic), and the row list is built one-per-chunk
  (`service.py:366-377`, asserted by `test_ingest_embeds_every_chunk_and_writes_one_row_each:76`).
  **Satisfied; no test that a changed file changes the count.**
- AC5 (one transaction): delete, `add_all` and `commit` run on one session with nothing in between — no
  query, so no autoflush point, and the CLI opens exactly one session per run
  (`backend/app/modules/srd/commands.py:65-72`). Under Postgres READ COMMITTED a concurrent `app srd status`
  sees the old corpus until commit, never a partial one. **Satisfied; only `len(db.executed) == 1` is
  asserted today, not the ordering or the absence of an earlier commit.**
- README already records replace-wholesale, one-transaction and restore-on-failure semantics
  (`backend/app/modules/srd/README.md`, "Surface" + "Notes"). Only the re-ingest sentence (same count,
  later time; a changed source changes file diff and count together, D3) is absent.

## Work items

**No production code change is needed.** One work item, backend-python, tests plus one README line.

- WI1 — proofs for AC1–AC5. In `backend/tests/srd/`, using the established monkeypatch seams
  (`_stub_source`, `srd_service.llm_service.embed_texts`, `count_tokens`; `tests/srd/test_ingest_service.py:57`):
  1. AC3: a source of several chunks with `EMBED_BATCH_SIZE` pinned to 1 and `embed_texts` raising on the
     second call — assert nothing was executed (the delete never ran), nothing added, no commit, source restored.
  2. AC5: record an ordered call log in `FakeWriteSession` — delete, then `add_all`, then exactly one commit,
     with no commit before the delete.
  3. AC4: chunk a fixture, add a heading to it, chunk again — chunk count changes with the file; a second
     `ingest` over the changed file writes exactly that many rows.
  4. AC1/AC2 on a real database, `@pytest.mark.database` over the existing `srd_db` fixture
     (`tests/srd/conftest.py`, `tests/database.py`) with `embed_texts` stubbed to zero vectors and a small
     fixture markdown: run `ingest` twice in one `asyncio.run`, assert equal count, distinct citations equal
     count, later `created_at`. Then a third run whose chunks carry a duplicated `(heading_path, ordinal)`:
     the commit raises, and count and ingest time still equal the second run's — AC3/AC5 against a real
     transaction. This is cheap; no gateway call.
  5. README: one sentence on re-ingest semantics.
- Live proof (~1 cent, real key present): `app srd status` → `app srd ingest` → `app srd status`; record
  same count, later time, and the distinct-citation SQL count. Evidence goes in `progress.md`.

## Interfaces

None new.

## Open questions

- AC1 compares two live runs against the upstream source. If upstream changed since this morning the count
  legitimately differs (that is D3 working as intended). Is a differing count acceptable evidence for AC1, or
  should the live proof be repeated until the source is stable?
