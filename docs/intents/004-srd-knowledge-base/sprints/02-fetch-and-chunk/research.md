---
author: fhit:architect
owner: agent
created: 2026-09-22
---
# Research: sprint 004-02 — fetch and chunk

## Facts

**Source.** `https://raw.githubusercontent.com/palikhov/cc-srd5-1/main/cc-srd5.md` — `curl -sIL`
today: `HTTP/2 200`, `content-length: 1878072` (1.79 MiB). CC-BY-4.0; its own first section is the
attribution sentence, verbatim usable for `LICENSE.md` (already quoted in
`backend/app/modules/srd/README.md:28`-`33`). Structure: 2098 headings, levels `#`=106, `##`=626,
`###`=987, `####`=362, no `#####`/`######`. Headings carry pandoc anchors —
`## Dragonborn {#section-dragonborn}` — which must be stripped from the heading path. Six table
lines in the whole file; stat blocks are `***Name.*** text` paragraphs, so no table handling is
needed. Section size: median 666 chars (~180 tokens), largest `## Adventuring Gear` at 26 964 chars
(~7 000 tokens); 81 sections are heading-only. Whole file ≈ 520 000 tokens.

**Embedding.** `openai/text-embedding-3-small`, 8191-token input window, tokenizer `cl100k_base`
(tiktoken `model.py` MODEL_TO_ENCODING, raw GitHub, 2026-09-22). Pinned in `.env.dist:53`,`:58` with
`EMBEDDING_DIMENSIONS=1536`; `embed_texts(texts, *, model=None) -> EmbeddingResult` exists
(`backend/app/core/llm/service.py:350`) but this sprint never calls it.

**Dependencies.** `tiktoken` is absent from `backend/uv.lock`; latest 0.14.0 (PyPI), needs adding to
`[project] dependencies` plus `make build`. `httpx` 0.28.1 is in the lock as a dev dep
(`backend/pyproject.toml:37`) and transitively under `langchain-core`/`langfuse`; since we import it
directly it is promoted to a runtime dependency in the same edit.

**Container.** `app-cli` bind-mounts `./backend:/app` (`compose.yaml:53`-`54`), so a file written to
`/app/content/srd/v1/` appears in the repo working tree — the diff AC3 wants.

**CLI precedent.** `srd_app = typer.Typer()`, one `@srd_app.command(...)` function, failures are one
line to stderr plus `raise typer.Exit(code=1) from exc`, never a traceback
(`backend/app/modules/srd/commands.py:29`,`:40`-`50`; same shape in
`backend/app/modules/content/commands.py:16`-`18`). `srd_app` is already wired (`backend/app/cli.py:40`).
`SRD_ROOT` mirrors `CONTENT_ROOT: Path = Path(__file__).resolve().parents[3] / "content"`
(`backend/app/modules/content/service.py:16`), monkeypatchable per test.

## Assumptions

- Source pinned to the `main` branch raw URL, not a commit SHA: D3 wants an upstream change to
  surface as a diff, which a SHA pin would hide. `SOURCE_URL`/`SOURCE_VERSION` (`"v1"`) are module
  constants.
- `MAX_CHUNK_TOKENS = 1000`, `CHUNK_OVERLAP_TOKENS = 100`. The window allows 8191, but 1000 keeps a
  retrieved passage quotable and splits only 47 of 2098 sections (~2160 chunks total). AC4 holds with
  a wide margin.
- Heading-only sections (no body text) produce no chunk.
- Tokens are counted through a `count_tokens()` module function so unit tests monkeypatch it and
  never reach tiktoken's BPE download; the real encoding is loaded lazily and cached.
- No qa agent: the dry run itself is the proof.

## Work items

**WI1 — fetch and store (backend-python).** `SRD_ROOT`, `SOURCE_URL`, `SOURCE_VERSION`,
`build_http_client()`, `fetch_source()`; `SrdSourceError` in `errors.py`; `tiktoken` + `httpx` in
`pyproject.toml`/`uv.lock`; `backend/content/srd/v1/LICENSE.md` with the CC-BY sentence and a
matching paragraph in the repository `README.md` (AC6). Tests: stores the body at
`SRD_ROOT/<version>/SRD_CC_v5.1.md` and returns that path; a second call overwrites; a non-2xx
response and a transport error each raise `SrdSourceError` and leave an existing file byte-identical.

**WI2 — chunking and the command (backend-python).** `RuleChunk` in `schemas.py`, `count_tokens()`,
`chunk_source()`; the `app srd ingest --dry-run` command printing stored path, byte count, chunk
count, total token count and a sample of heading paths, mapping `SrdSourceError` to one stderr line
and exit 1 (AC1, AC2, AC5). `--dry-run` is required in this sprint: without it the command exits 1
saying embedding lands in sprint 03. Tests: a small fixture yields `Combat › Cover › Half Cover`
with anchors stripped; an oversized section yields ordinals 0..n sharing one heading path with
overlapping text and every chunk `<= MAX_CHUNK_TOKENS`; heading-only sections drop; the command
prints the counts with `fetch_source` monkeypatched to a fixture (CliRunner).

## Interfaces

Both WIs code against these verbatim; WI2 never calls the network.

```python
# app/modules/srd/service.py
SRD_ROOT: Path = Path(__file__).resolve().parents[3] / "content" / "srd"
SOURCE_URL: str = "https://raw.githubusercontent.com/palikhov/cc-srd5-1/main/cc-srd5.md"
SOURCE_VERSION: str = "v1"
SOURCE_FILENAME: str = "SRD_CC_v5.1.md"
MAX_CHUNK_TOKENS: int = 1000
CHUNK_OVERLAP_TOKENS: int = 100

def build_http_client() -> httpx.Client: ...          # WI1, the test seam (httpx.MockTransport)
def fetch_source(*, version: str = SOURCE_VERSION) -> Path: ...   # WI1
def count_tokens(text: str) -> int: ...               # WI2, cl100k_base
def chunk_source(path: Path) -> list[RuleChunk]: ...  # WI2

# app/modules/srd/schemas.py — WI2
class RuleChunk(CamelModel):
    heading_path: str
    ordinal: int
    text: str
    token_count: int

# app/modules/srd/errors.py — WI1
class SrdSourceError(SrdError): ...   # unreachable, non-2xx, unwritable or unparseable source
```

Chunking rule: walk `#`..`####` in order, maintaining the open heading stack; `heading_path` is the
stack's titles — anchors `{#...}` and surrounding whitespace stripped — joined with `" › "`. A
section's body is the text between its heading and the next heading of any level. Body under
`MAX_CHUNK_TOKENS` → one chunk, `ordinal = 0`. Otherwise split on token boundaries into pieces of at
most `MAX_CHUNK_TOKENS` with `CHUNK_OVERLAP_TOKENS` repeated from the previous piece, all sharing the
heading path, `ordinal` counting 0, 1, 2 … `token_count` is the chunk's own token count.

## Open questions

None product-visible; the citation surface and the attribution's player-facing placement stay open in
the intent research and are not touched here.
