---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 02 — fetch and chunk

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The SRD 5.1 CC-BY markdown is fetched and stored under `backend/content/srd/v1/`, split into citable heading-path chunks, and `app srd ingest --dry-run` reports path, bytes, chunk count, token count and sample heading paths; `LICENSE.md` and repository `README.md` carry the attribution; `tiktoken` and `httpx` become runtime deps | fetch stores at `SRD_ROOT/<version>/SRD_CC_v5.1.md` and overwrites on re-run; non-2xx and transport error raise `SrdSourceError` and leave an existing file untouched; fixture yields `Combat › Cover › Half Cover` with pandoc anchors stripped; oversized section splits into ordinals 0..n sharing one heading path, each `<= MAX_CHUNK_TOKENS`; heading-only sections yield no chunk; command prints counts with `fetch_source` monkeypatched, and maps `SrdSourceError` to one stderr line + exit 1 | – |

One WI, not two: both halves edit `service.py` and `errors.py`, and parallel implementers in one checkout already swept files into each other's commits in sprint 01. The human asked for a quick sprint with minimal tests, so the unit tests above are the whole set — no qa agent; the live dry-run is the proof.

## Interfaces
```python
# app/modules/srd/service.py
SRD_ROOT: Path = Path(__file__).resolve().parents[3] / "content" / "srd"
SOURCE_URL: str = "https://raw.githubusercontent.com/palikhov/cc-srd5-1/main/cc-srd5.md"
SOURCE_VERSION: str = "v1"
SOURCE_FILENAME: str = "SRD_CC_v5.1.md"
MAX_CHUNK_TOKENS: int = 1000
CHUNK_OVERLAP_TOKENS: int = 100

def build_http_client() -> httpx.Client: ...          # test seam (httpx.MockTransport)
def fetch_source(*, version: str = SOURCE_VERSION) -> Path: ...
def count_tokens(text: str) -> int: ...               # cl100k_base, lazily loaded, monkeypatchable
def chunk_source(path: Path) -> list[RuleChunk]: ...

# app/modules/srd/schemas.py
class RuleChunk(CamelModel):
    heading_path: str
    ordinal: int
    text: str
    token_count: int

# app/modules/srd/errors.py
class SrdSourceError(SrdError): ...   # unreachable, non-2xx, unwritable or unparseable source
```

Chunking rule: walk `#`..`####` in order with an open heading stack; `heading_path` = stack titles (anchors `{#...}` and whitespace stripped) joined with `" › "`. Body = text between a heading and the next heading of any level. Body `<= MAX_CHUNK_TOKENS` → one chunk, ordinal 0; else token-boundary pieces of at most `MAX_CHUNK_TOKENS` with `CHUNK_OVERLAP_TOKENS` repeated from the previous piece, ordinals 0, 1, 2 …; `token_count` is the chunk's own count.

CLI: `app srd ingest --dry-run` = fetch + store + chunk + report, no DB, no embedding. Without `--dry-run` the command exits 1 saying embedding lands in sprint 03.

## Acceptance tests (qa)
None — see above. AC1–AC6 are proven by the developer's live dry-run recorded in `progress.md` plus WI1's unit tests.

## Order
WI1 alone.
