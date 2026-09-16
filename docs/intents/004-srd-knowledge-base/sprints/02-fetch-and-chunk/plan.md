---
author: sprint
owner: agent
created: 2026-09-16
---
# Plan: Sprint 02 — fetch and chunk

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The rules document arrives from its public source and lands in the repository at a fixed place, replacing what was there; a failed download says so and leaves the stored copy untouched. | stores at the expected path, creating parents; a second run overwrites in place; non-200, timeout and empty body each raise `SrdSourceError` while an existing file stays byte-identical; no network in tests | I1 |
| 2 | backend-python | The stored document becomes citable passages: each carries the heading trail it sits under and a position, and none is too long to embed. | heading path ` › `-joined and anchor-free; ordinals from 0 per section; a heading-only section yields no passage; an oversized section yields several sharing the parent path, ascending ordinals, overlapping text; none exceeds the cap | I1 |
| 3 | backend-python | An operator can ask what a rules import would do without doing it: where the file landed, how big it is, how many citable passages it holds, what they are called. | all five appear; a source failure gives one stderr line and exit 1, no traceback; without the flag, exit 1 saying embedding is not landed; no database session opened | I1, I2, I3 |
| 4 | backend-python | The rules text ships in the repository with its licence, and the required attribution is stated where a reader of the project will find it. | the shipped tree carries the document and its licence file; the licence file holds the CC-BY-4.0 sentence and URL; the repository README states the attribution | – |
| qa | qa | Black-box acceptance tests, one per criterion. | below | I1, I2, I3 |

## Interfaces
- **I1** — in `backend/app/modules/srd/service.py`: `SRD_ROOT: Path = Path(__file__).resolve().parents[3] / "content" / "srd"`; `SOURCE_URL = "https://raw.githubusercontent.com/palikhov/cc-srd5-1/main/cc-srd5.md"`; `SOURCE_VERSION = "v1"`; `SOURCE_FILENAME = "SRD_CC_v5.1.md"`; `def fetch_source(*, version: str = SOURCE_VERSION) -> Path`. `errors.py`: `class SrdSourceError(SrdError)`. The fetch goes through a module-level `httpx` reference so tests monkeypatch it, as `build_sdk_client` is today; `httpx` moves from the dev group into the runtime dependencies.
- **I2** — in `service.py`: `EMBEDDING_WINDOW_TOKENS = 8192`, `MAX_CHUNK_TOKENS = 800`, `CHUNK_OVERLAP_TOKENS = 100`; `def count_tokens(text: str) -> int`; `def chunk_source(path: Path) -> list[RuleChunk]`. `schemas.py`: `class RuleChunk(CamelModel): heading_path: str; ordinal: int; text: str; token_count: int`. `tiktoken` becomes a dependency, its BPE table pre-warmed in `docker/backend.Dockerfile` — it downloads on first use and the suite must not touch the network.
- **I3** — `schemas.py`: `class IngestReport(CamelModel): source_version: str; source_bytes: int; chunk_count: int; token_count: int; cost_usd: float | None = None`. `commands.py`: `@srd_app.command("ingest")` taking `dry_run: bool = typer.Option(False, "--dry-run")`.
- **I4** — `backend/content/srd/v1/SRD_CC_v5.1.md` (committed, ~1.9 MB) and `backend/content/srd/v1/LICENSE.md`; the repository `README.md` attribution sentence.

## Acceptance tests (qa)
- AC1 → the dry run writes `backend/content/srd/v1/SRD_CC_v5.1.md` and prints the stored path and byte count.
- AC2 → the same run prints passage count, token total and sample heading paths shaped like `Combat › Cover › Half Cover`.
- AC3 → re-running overwrites the stored file in place; an unchanged source leaves the working tree clean.
- AC4 → no passage exceeds the cap; an oversized section splits with overlap, keeping its parent heading path and gaining an ordinal.
- AC5 → an unreachable or unparseable source exits non-zero with the source error's message, no traceback, stored file untouched.
- AC6 → the licence file holds the CC-BY-4.0 attribution sentence and the repository README states it too.

## Order
Parallel: WI1, WI4, qa. Then WI2, then WI3 — WI1 and WI2 share `service.py`, `schemas.py` and the dependency list, and all work items share one checkout.
