---
author: fhit:architect
owner: agent
created: 2026-09-15
---
# Research: intent 004 — SRD knowledge base

## Facts

**What phase 2 left us.** The seam is `core/llm/` module functions returning LangChain objects
(`backend/app/core/llm/service.py:62`,`:88`), eight classified `LlmError` codes (`…/llm/errors.py`), a Typer
command per call kind (`…/llm/commands.py:18`, wired `backend/app/cli.py:28`). **The embedding call does not
exist yet** — backlog 04 is `open` (`docs/intents/001-llm-access-scaffolding/backlog.md:17`), its shape fixed
as `embed_texts(texts) -> vectors + usage`, direct to `/api/v1/embeddings`, no `dimensions` parameter
(`…/sprints/04-embedding-round-trip/brief.md:18`,`:24`). **No sprint here can start before it lands.**
`Settings` declares `chat_model` only (`backend/app/core/settings.py:16`); `EMBEDDING_MODEL=
openai/text-embedding-3-small` and `EMBEDDING_DIMENSIONS=1536` sit in the owner-only `.env.dist:37`,`:42`,
become declared fields with 04, and **phase 4 must not pick a different model** (`…/Stage-01/README.md:313`).

**Storage is largely pre-ruled.** Postgres runs `pgvector/pgvector:pg16` (`compose.yaml:76`); no extension, no
vector column — the baseline holds `users`/`sessions` only (`backend/alembic/versions/0001_baseline.py`), and
revisions are a linear chain, one `env.py` import per module (`backend/alembic/env.py:11`-`13`).
`docs/general/model.md:38`,`:59`-`62` names the entity **`SrdRule`**: owned by nobody, rebuilt by an ingest
CLI, "replaced wholesale by a re-ingest", "cites a section and a position within it"; `:211`-`222` rules one
embedding model, two tables (SRD, journal), every vector row recording **which model embedded it**. Source
belongs at `backend/content/srd/` (`model.md:245`, reserved `…/phase-01/shared-knowledge.md:550`) — that
directory does not exist, and **no vendored SRD content and no fetch script exist anywhere in the repo**. The
consumer is the phase-8 tool `lookup_rule(query)` (`docs/general/architecture.md:68`); only SRD text goes
through RAG (`AGENTS.md:42`), and the glossary pins the corpus as **SRD 5.1, CC-BY-4.0** (`…/glossary.md:17`).
Two roadmap open decisions are owned by **this phase** (`…/Stage-01/README.md:313`-`:314`): the migration's
vector width, and how a fixture-local real engine is driven — the latter collides with the landed "fully
synchronous suite, never construct an engine" rule (`backend/tests/conftest.py:1`-`14`) and may amend it.
Versioned file-backed loader plus Typer command precedent: `backend/app/modules/content/service.py:16`-`18`.

**External** (docs-lookup, 2026-09-15; none installed). `pgvector` (Python) 0.5.0 — PyPI — gives
`pgvector.sqlalchemy.VECTOR`, `cosine_distance()` for `ORDER BY`, HNSW via `postgresql_using='hnsw'` +
`postgresql_ops={'embedding':'vector_cosine_ops'}` (context7 /pgvector/pgvector-python).
`langchain-text-splitters` 1.1.2 (`MarkdownHeaderTextSplitter`, `RecursiveCharacterTextSplitter`), `tiktoken`
0.14.0 — PyPI. SRD 5.1 is CC-BY-4.0 since 2023-01 and the first-party download (dnd.wizards.com →
dndbeyond.com/resources/1781) is a **PDF**; mirrors are `palikhov/cc-srd5-1` (CC-BY-4.0, one heading-structured
`cc-srd5.md`, full SRD 5.1 prose), `Tabyltop/CC-SRD` (CC-BY-4.0, whole-document `.json`/`.html`/`.txt` plus a
monsters JSON) and `5e-bits/5e-database` (**OGL 1.0a, not CC-BY** — entity records, not prose). CC-BY obliges
us to carry the attribution sentence.

## Options

**1 — Source data.** Recommendation **B**: vendor the markdown at `backend/content/srd/v1/` in one commit with
its attribution file; a `Makefile` target documents the manual refresh.

| Option | Pro | Con |
|---|---|---|
| A official PDF | first-party; page numbers are natural citations | needs a PDF-parser dep; two-column extraction is lossy; no headings to chunk on |
| B **vendored markdown** (`cc-srd5-1`) | headings are chunk boundaries *and* citations; diffable; reproducible forever (`…/README.md:264`) | ~1 MB in git; a third party's transcription; wants a spot-check |
| C scripted fetch at ingest | no blob in git | a save stops being reproducible; network in the ingest path; upstream can vanish |
| D structured JSON (`5e-bits`) | machine-readable fields | **OGL, not CC-BY** — conflicts with the glossary; records, not the prose a rules question needs |

**2 — Chunking.** Recommendation **C**. A citation is only as good as its heading path: markdown yields a path
(`Combat › Cover › Half Cover`) where the PDF would have yielded a page number.

| Option | Pro | Con |
|---|---|---|
| A by heading/section | one rule per chunk; citation is free | sections run from 2 lines to whole monster lists — some blow the embedding window |
| B fixed token window + overlap | uniform, trivially correct | cuts mid-rule; citation degrades to "somewhere in chapter 9" |
| C **hybrid** — headings first, token-split the oversized with overlap, each part keeping the parent heading path + ordinal | citable and bounded; the ordinal is `model.md:62`'s "position within it" | two stages; needs `tiktoken` |

**3 — Storage.** Ruled already by `model.md:38`,`:211`: an **`SrdRule` table in the existing postgres**,
`VECTOR(1536)`, extension plus HNSW cosine index in the migration, model name on every row. sqlite-vec or a
local FAISS/numpy index would add a second datastore and backup story for a corpus that already has a
database. Not re-opened; the width literal and the mismatch check are open questions below.

**4 — Retrieval shape.** Recommendation: `search_rules(query, *, limit) -> list[RuleMatch]`, a module function
in its own `modules/srd/`, plus a Typer command to exercise it by hand — the shape of `content validate`.
`RuleMatch` carries passage text, citation (heading path + ordinal), similarity score and embedding model:
enough for the agent to quote and for a player-facing citation later, nothing more. *Rejected — an HTTP
endpoint:* the only consumer is the phase-8 tool binding, phase 4 ends without a screen by design
(`…/Stage-01/README.md:337`), and a public rules-search API is a surface nothing asks for.

**5 — Re-ingestion and the empty corpus.** Recommendation: **delete-all + insert in one transaction** —
idempotent by construction, no stale rows, readers never see half a corpus, matching "replaced wholesale by a
re-ingest" (`model.md:60`); the cost is re-embedding everything each run (cents, minutes). *Rejected:* a
per-chunk content-hash upsert needs a chunk id stable across re-chunking, which is what re-chunking breaks;
versioned corpora add a second versioning axis beside content `v<n>` for a CLI nobody runs during play. Empty
corpus: `search_rules` returns `[]` rather than raising, `app srd status` (row count, model, ingested-at)
makes the state visible, and what the *DM* then says is a product decision below.

## Recommendation

Vendor the CC-BY markdown at `backend/content/srd/v1/` with its attribution file; chunk hybrid (headings
first, token-split the oversized, heading path + ordinal on every chunk); store in an `SrdRule` table with
`VECTOR(1536)` and an HNSW cosine index; expose `search_rules()` plus `app srd ingest` / `search` / `status`;
re-ingest by wholesale replace in one transaction; empty corpus returns no matches, never an error. Sequenced
behind backlog 04 (the embedding call), which is still open.

## Open questions

*product-visible*
- **Citation surface** — inline "(SRD: Cover)" in the narration, a separate sources panel, or developer-trace
  only? Decides whether `RuleMatch` needs a display label beside the path.
- **Empty or weak result** — when nothing clears the relevance floor, does the DM say "I found no rule for
  that", answer from the model's own knowledge, or refuse to rule? Trustworthy DM versus plausible one.
- **Attribution** — CC-BY obliges carrying the SRD 5.1 sentence: player-visible (About/credits, footer) or
  repository `LICENSE` only?
- **Before any ingestion** — a fresh install has an empty corpus: refuse to start a playthrough, start with a
  visible warning, or play on with an unaided DM?
- **How many passages** a lookup returns, and whether the player ever sees more than one.

*technical*
- Vector width in the migration: hardcoded `1536` versus reading `EMBEDDING_DIMENSIONS`, and where the
  mismatch check lives (`…/Stage-01/README.md:313` assigns this here).
- How ingest/search tests get a real engine against a suite that never builds one (`…/README.md:314`) — may
  amend a landed decision; phase 3 inherits the answer.
- Whether the vendored markdown needs a correctness spot-check, and against what.
