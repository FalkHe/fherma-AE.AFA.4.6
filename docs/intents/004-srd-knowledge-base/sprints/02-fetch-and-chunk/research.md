---
author: fhit:architect
owner: agent
created: 2026-09-16
updated: 2026-09-16
---
# Research: sprint 004/02 — fetch and chunk

## Facts

**What 01 landed.** `srd/service.py` holds `check_vector_width`, `corpus_status`, `require_corpus` only — no
path, no constant, no `Path` import (`backend/app/modules/srd/service.py:1`-`50`). `errors.py` has
`SrdError`/`SrdCorpusEmptyError`/`SrdVectorWidthError` — **no `SrdSourceError`** (`…/errors.py:1`-`10`).
`schemas.py` has `CorpusStatus` only, on `CamelModel` (`…/schemas.py:6`). `commands.py` has `srd_app` with one
`status` command and the failure shape this sprint copies: one stderr line plus `typer.Exit(code=1)`, never a
traceback (`…/commands.py:29`,`:44`-`:50`). `EMBEDDING_WIDTH = 1536` lives in `models.py:13`.

**`CONTENT_ROOT` precedent.** Declared `CONTENT_ROOT: Path = Path(__file__).resolve().parents[3] / "content"`
(`backend/app/modules/content/service.py:16`); repointed in tests by `monkeypatch.setattr(service,
"CONTENT_ROOT", tmp_path)` through the module reference (`backend/tests/content/conftest.py:291`-`293`); read
via the module (`content/commands.py:11`). `SRD_ROOT` mirrors this exactly. `backend/` is bind-mounted into
`app-cli` (`compose.yaml:55`), so a CLI write lands in the working tree and AC3's `git diff` works — but the
image declares no `USER`, so the written file is root-owned on the host (`docker/backend.Dockerfile`).

**HTTP client.** `httpx` 0.28.1 is in the lock as a *transitive runtime* dependency of `langchain-core` 1.6.3
(`backend/uv.lock:423`,`:330`) and is declared only in the dev group (`backend/pyproject.toml:31`). The llm seam uses the OpenRouter SDK, not raw HTTP; tests fake the
network by monkeypatching `service.build_sdk_client` onto an `httpx.MockTransport` client
(`backend/tests/core/llm/test_embeddings.py:12`,`:52`) — the same shape works here via a module-level
`httpx.get`. httpx 0.28.1 — local (`uv.lock`).

**`tiktoken` is not a dependency** (absent from `uv.lock`), nor is `langchain-text-splitters`. Cost of adding
it: `tiktoken` + `regex`, and — decisive — `tiktoken.encoding_for_model("text-embedding-3-small")` resolves to
`cl100k_base` (`tiktoken/model.py:47`) whose BPE file is **downloaded over HTTPS from
`openaipublic.blob.core.windows.net` at first use**, cached only if `TIKTOKEN_CACHE_DIR` is set
(`tiktoken/load.py:15`-`17`,`:35`-`40`; source — github.com/openai/tiktoken). Mitigation: set `TIKTOKEN_CACHE_DIR` and pre-warm the cache in
`docker/backend.Dockerfile`, one `RUN` line; then the suite is offline again.

**Embedding window.** `EMBEDDING_MODEL` defaults to `openai/text-embedding-3-small`
(`backend/app/core/settings.py:20`); OpenRouter reports `context_length: 8192` and `$0.00000002`/token for it
(`https://openrouter.ai/api/v1/embeddings/models`, fetched 2026-09-16).

**The source.** `https://raw.githubusercontent.com/palikhov/cc-srd5-1/main/cc-srd5.md` — HTTP 200,
**1,878,072 bytes** (46,413 lines, ~468k tokens ≈ **$0.01** to embed whole). Unchanged since 2023-02-23, so
AC3's "unchanged upstream leaves the tree clean" holds in practice. Headings: 17 `#`, 106 `##`, 626 `###`, 987
`####`. Splitting at every heading gives **2,098 sections**: median body 664 chars, largest 26,962 chars
(~7k tokens — *under* the 8192 window), 64 over ~800 tokens, 268 under 200 chars, and **72 with no body at
all**. 124 headings carry a `{#anchor}` suffix that must be stripped from the citable path. The file opens
with the CC-BY attribution sentence itself (line 3) and the repo ships `licensing/CC-BY-4.0.txt`.

**Consequence for AC4:** at the model's own 8192-token window nothing would ever split, making AC4 untestable
against the real corpus. A `MAX_CHUNK_TOKENS` well below the window (proposal: 800, overlap 100) makes the
split real *and* retrieval usable — a 7k-token "Adventuring Gear" chunk is a bad citation.

## Work items

- **WI1 — the source arrives and is stored.** Fetch over HTTP, write under `SRD_ROOT/<version>/`, return the
  path. Tests: stores at the expected path and creates parents; a second run overwrites in place; a non-200,
  a timeout and an empty body each raise `SrdSourceError` leaving an existing file byte-identical; nothing
  touches the network in tests (faked at the module-level client).
- **WI2 — the stored file becomes citable chunks.** `RuleChunk`, heading-path assembly, token counting, the
  oversize split, plus the dependency and its Docker cache pre-warm. Tests: path is ` › `-joined and
  anchor-free; ordinals run from 0 per section; a heading-only section yields no chunk; an oversized section
  yields several chunks sharing the parent path with ascending ordinals and overlapping text; no chunk exceeds
  `MAX_CHUNK_TOKENS`.
- **WI3 — the operator sees what would be embedded.** `app srd ingest --dry-run`: stored path, byte count,
  chunk count, total tokens, a sample of heading paths. Tests: all five appear; `SrdSourceError` gives one
  stderr line and exit 1, no traceback; the bare command (no flag) exits 1 naming that embedding is not
  landed; no database session is opened.
- **WI4 — attribution, and the corpus in git.** Commit the fetched markdown, `backend/content/srd/v1/
  LICENSE.md`, the repository `README.md` sentence, and the `srd` module README's Surface section. Tests: the shipped tree carries both
  files and `LICENSE.md` holds the CC-BY sentence and URL (shape of `tests/content/test_shipped_tree.py`).

WI1 and WI2 are parallel (WI2 chunks a fixture, never a download); WI3 needs both; WI4 is independent.

## Interfaces

In `backend/app/modules/srd/service.py`:

```python
SRD_ROOT: Path = Path(__file__).resolve().parents[3] / "content" / "srd"
SOURCE_URL = "https://raw.githubusercontent.com/palikhov/cc-srd5-1/main/cc-srd5.md"
SOURCE_VERSION = "v1"
SOURCE_FILENAME = "SRD_CC_v5.1.md"
EMBEDDING_WINDOW_TOKENS = 8192
MAX_CHUNK_TOKENS = 800
CHUNK_OVERLAP_TOKENS = 100

def fetch_source(*, version: str = SOURCE_VERSION) -> Path: ...   # WI1
def count_tokens(text: str) -> int: ...                            # WI2
def chunk_source(path: Path) -> list[RuleChunk]: ...               # WI2
```

`schemas.py` (WI2): `class RuleChunk(CamelModel): heading_path: str; ordinal: int; text: str; token_count: int`.
`schemas.py` (WI3): `class IngestReport(CamelModel): source_version: str; source_bytes: int; chunk_count: int;
token_count: int; cost_usd: float | None = None`. `errors.py` (WI1): `class SrdSourceError(SrdError)`.
`commands.py` (WI3): `@srd_app.command("ingest")` with
`dry_run: bool = typer.Option(False, "--dry-run")`. Fetch goes through a module-level `httpx` reference so
tests can monkeypatch it, as `service.build_sdk_client` is monkeypatched.

## Open questions

*product-visible*
- **Committing a 1.9 MB rules document.** The corpus text lands in the repository forever, ~1.9 MB per
  revision. Acceptable, or should the file be kept out of git and re-fetched on demand (which costs D3's
  reviewable diff)?
- **Which transcription we trust.** A volunteer conversion of the publisher's PDF, unchanged since February
  2023, carrying its own "work in progress, no guarantees" warning. Spot-check a few rules first?

*technical*
- `MAX_CHUNK_TOKENS = 800` / `CHUNK_OVERLAP_TOKENS = 100` are proposals, not measurements — the floor in
  backlog 06 is the first place the choice is testable. **ASSUMPTION** unless vetoed.
- The 268 sub-200-character sections stay as their own chunks rather than being merged upward; merging would
  blur the citation. **ASSUMPTION**.
- A CLI-written file is root-owned on the host (no `USER` in the backend image). Left as is, documented.
- `httpx` moves from the dev group to the runtime dependencies, where its use now puts it.
