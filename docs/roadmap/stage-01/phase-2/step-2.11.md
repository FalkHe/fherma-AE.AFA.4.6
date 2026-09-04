---
phase: 2
step: "2.11"
title: "Source adapters: Wikipedia + web search"
summary: The Wikipedia adapter (REST search lookup with the matched title recorded, page HTML→Markdown, page-image URL + attribution) and the Tavily search adapter behind a SearchProvider protocol with the pinned per-source-type query templates; `app ingest probe` prints candidates without DB writes.
effort: 4
dependencies: ["2.10"]
agent: backend-dev
track: backend
---

# Step 2.11 — Source adapters: Wikipedia + web search

**Effort: 4** — two external integrations with real-world messiness
(disambiguation, missing keys, flaky results), all behind clean seams.

**Required reading before any code:**
[`shared-knowledge.md`](shared-knowledge.md) — *Ingestion decisions* is the
spec: the three Wikipedia REST endpoints, the Tavily call shape (plain HTTPX,
no SDK), the `SearchProvider` protocol requirement, the exact query
templates + source-type mapping, result caps, and the missing-key rule
(Wikipedia-only with a warning — never a failure). Zero deviations; stop and
report if one seems necessary.

## Files

- Create `backend/app/services/ingestion/wikipedia.py`, `search.py`
- Create fixture-based tests under `backend/tests/services/ingestion/`
- Modify `backend/app/cli/ingest.py` (`probe` command),
  `backend/app/core/config.py`, `.env.dist` (pinned 2.11 keys)

## Implementation outline

- `wikipedia.py`: search lookup (`rest.php/v1/search/page`, limit 3, best
  hit; **record the matched title** — it becomes `source_title` so the admin
  sees what was matched, the disambiguation guard), page HTML via
  `page/html/{key}` → 2.10 extract, image URL from `page/summary/{key}`
  (`originalimage.source`), then the **pinned two-call attribution chain**
  (shared-knowledge → *Ingestion decisions*): file title via
  `prop=pageimages&piprop=name`, licence/artist via Commons
  `prop=imageinfo&iiprop=extmetadata` — strip the HTML in `Artist`/`Credit`,
  compose the pinned attribution string, `null` when metadata is missing.
  No hit = typed "no Wikipedia match" result.
- `search.py`: `SearchProvider` protocol + `TavilySearchProvider`
  (`POST https://api.tavily.com/search` via the 2.10 HTTPX client). Runs the
  three pinned templates, top 2 each, ≤ `INGESTION_MAX_WEB_DOCUMENTS`,
  deduped by URL, each candidate tagged with its template's `source_type`.
  Missing `TAVILY_API_KEY` → empty result + structured warning.
- `app ingest probe "<name>"`: prints matched Wikipedia title, image URL,
  and the typed search candidates — no DB writes.
- Tests: recorded/fixture JSON responses; no network.

## Verification

- `make backend-test` green. Manual: `app ingest probe "Suzuki GSR 600"`
  prints the matched title, an image URL, and ≥3 typed candidates; with
  `TAVILY_API_KEY` unset it prints Wikipedia results plus the warning.

**On finish:** append cross-step decisions to `shared-knowledge.md` →
*Landed decisions*.
