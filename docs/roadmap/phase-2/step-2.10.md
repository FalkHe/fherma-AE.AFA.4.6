---
phase: 2
step: "2.10"
title: Fetch & extract core
summary: The HTTPX fetch layer (timeouts, size caps, content-type checks, per-domain politeness delay) and trafilatura→normalized-Markdown extraction with raw-payload retention under DATA_DIR, verified via an `app ingest fetch-url` dev command — tests run on saved HTML fixtures, never the network.
effort: 3
dependencies: ["0.1"]
agent: backend-dev
track: backend
---

# Step 2.10 — Fetch & extract core

**Effort: 3** — self-contained utility layer; no DB models involved.
Independent of the 2.1→2.3 mainline — parallelizable in a second backend
session.

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *Ingestion decisions* (fetch
limits, User-Agent, PDF rule, data-dir layout) and *Config keys*.
`docs/architecture.md` → *Ingestion*. Zero deviations; stop and report if one
seems necessary.

## Files

- Create `backend/app/services/ingestion/__init__.py`, `fetch.py`,
  `extract.py`, `storage.py`
- Create `backend/app/cli/ingest.py` (`fetch-url` dev command)
- Create `backend/tests/services/ingestion/` (HTML fixtures + tests)
- Modify `backend/app/core/config.py`, `.env.dist` (pinned 2.10 keys),
  `backend/pyproject.toml` + `uv.lock` (`httpx` runtime, `trafilatura`),
  `backend/app/cli/main.py`, `.gitignore` (`backend/var/`)

## Implementation outline

- `fetch.py`: async HTTPX client — 20 s timeout, 5 MiB cap (stream +
  abort), `text/html` only (PDF and others: skip with a structured warning),
  follow redirects, 1 s per-domain politeness delay, pinned User-Agent.
  Returns a result object (final URL, status, body, content-type) or a typed
  failure — callers decide severity.
- `extract.py`: trafilatura main-text extraction → normalized Markdown
  (headings preserved — 2.18's chunker splits on them); empty extraction is
  a typed failure, not an exception.
- `storage.py`: persist raw payloads to
  `DATA_DIR/sources/{motorbike_id}/{document_id}.html`; returns the
  DATA_DIR-relative path (what `source_documents.raw_path` stores).
- `app ingest fetch-url <url>`: fetch + extract + print Markdown, retain the
  raw payload — the manual smoke tool.
- Tests: fixture HTML files, monkeypatched transport; **never the network**.
- Run `make build` after the dependency change.

## Verification

- `make backend-test` green. Manual:
  `app ingest fetch-url https://en.wikipedia.org/wiki/Suzuki_GSR600` prints
  Markdown and leaves the raw payload under `backend/var/data/sources/`;
  an oversized/wrong-content-type URL is refused with the typed warning.

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*.
