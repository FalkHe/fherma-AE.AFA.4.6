# Retrieval and the advisor agent

The path from a customer's sentence to a grounded reply.

```text
utterance
  → query translation        (LLM, json_schema, temperature 0)
  → candidate scoping        (name resolution ∪ spec filters)
  → hybrid retrieval         (FTS + pgvector, RRF per query)
  → second RRF fusion        (across queries)
  → retrieve_bike_knowledge  (the tool the model actually calls)
  → advisor loop             (bind_tools, ≤ 8 rounds, 120 s)
  → chat.respond job         (persists the assistant message)
```

## Hybrid retrieval

`retrieval_service.search(session, query_text, *, motorbike_ids=None,
limit=10)` is the sole entry point. It embeds the query, then runs **one SQL
statement**: a lexical CTE (`ts_rank` over the stored `text_tsv`,
`plainto_tsquery('english')`) and a semantic CTE (pgvector cosine `<=>`), each
`row_number()`-ranked and capped at `RETRIEVAL_CANDIDATES_PER_LEG` (50),
`FULL OUTER JOIN`ed and fused:

```text
score = coalesce(1/(RRF_K + rank_lex), 0) + coalesce(1/(RRF_K + rank_sem), 0)
```

`RRF_K = 60`. Order `score DESC, chunks.id`. No Python post-filter or re-sort.

Filters are applied **inside both legs** — model `status = 'approved'`,
`embedding IS NOT NULL`, `embedding_model = settings.embedding_model`, and the
optional id scope — so a scoped search still returns `limit` rows instead of
filtering a global top-50 down to nothing.

Returns frozen `RetrievedChunk`s carrying `chunk_id`, `motorbike_id`, `text`,
`score`, `source_document_id`, `source_url`, `source_title`, `heading_path`,
`page_number`, `sequence`. Raises `MissingApiKeyError`, or
`StaleEmbeddingsError` (naming `app embeddings rebuild`) when the configured
dimensions no longer match the column. A blank query or `motorbike_ids=[]`
returns `[]` without a call. Commits nothing.

CLI: `app retrieval search "<text>" [--bike <id>] [--limit n]`.

## Query translation

`llm/query_translation.py` on `CHAT_MODEL`, `with_structured_output(method=
"json_schema")`, temperature 0. The prompt (`query_translation.md`) receives the
utterance, an optional history summary and the chat's active preferences — all
fenced as untrusted.

`TranslatedQuery` yields:

- `search_queries` — ≤ 3, deduped, ≤ 200 chars each;
- `spec_filters` — `SpecFilters`: `categories[]`, `engine_cc_min/max`,
  `power_kw_min/max`, `wet_weight_kg_max`, `seat_height_mm_max`, `a2_eligible`,
  `price_bands[]`;
- `target_motorbike_names` — ≤ 5.

`a2_eligible = False` is a real constraint, not an absent one. A drift guard
asserts `FILTERABLE_SPEC_FIELDS + UNFILTERED_SPEC_FIELDS == SPEC_FIELDS`, so
adding a spec column forces a decision about whether it is filterable.

Structured-output rule: nested objects need `additionalProperties: false`
(walked over `$defs`); the root stays open. Tool argument schemas are exempt —
LangChain inlines their `$defs`.

## Pipeline

`rag_pipeline_service.retrieve(session, utterance, *, preferences=(),
history_summary="", limit=10) -> RagResult(queries, applied_filters,
candidate_motorbike_ids, chunks)`:

1. translate;
2. candidates = resolved names **∪** rows matching the spec filters (union, not
   intersection — a named bike stays in scope even if it misses a filter);
3. fan every `search_query` through `retrieval_service.search`, scoped to those
   candidates;
4. fuse across queries with a second RRF pass, dedupe by chunk id.

Degradation, all deliberate:

| Situation | Behaviour |
|---|---|
| Translation fails or returns nothing | raw utterance, no filters, unscoped (logged, not raised) |
| Filters stated but nothing matches | **no search at all**, empty chunks — this is what lets the advisor offer to widen |
| No filters and no names | unscoped search |
| Missing key / stale embeddings | propagate; the tool wrapper records a `failed` call |

`find_motorbike_ids` joins `motorbikes` to `motorbike_specs` with
`status='approved'` and `kind='verified'`, one clause per stated bound. A NULL
spec value never matches.

CLI: `app rag ask "<utterance>" [--summary] [--limit]`.

## Tools

Eight, in registry order. `ToolSpec(name, description, args_schema, run,
model_view)`; `execute(spec, ctx, arguments)` is the single execution path for
both the agent loop and `app tools run`: validate → run → dump camelCase →
record → return. Failures are recorded too (a `ValidationError` is not).
`ToolContext` carries the session, the chat and a `ToolCallCollector`. Tools
call services only — **no SQL in a tool**. An unresolvable or unapproved
reference returns the shared sentinel `{"unknownBike": "<reference verbatim>"}`.

| Tool | Kind | Arguments | Result |
|---|---|---|---|
| `catalogue_search` | read | `SpecFilters` | `{results[≤12], totalCount}` — id, name, category, powerKw, wetWeightKg, seatHeightMm, priceBand |
| `spec_comparison` | read | `motorbikeIds[]`, `names[]` (2–4 total) | `{bikes[], rows[]}` over the 13 frozen spec fields, nulls explicit |
| `licence_fit_check` | read | id **or** name, `licence` `A2`/`A`, `riderHeightCm`, `insideLegMm`, `experience` | `{rules[]}` with verdict `pass`/`fail`/`unknown` + evidence |
| `cost_estimator` | read | id **or** name, `annualKm` (0–60 000, default 8000) | `{currency, lineItems[], total, assumptions[], coefficientsVersion}` |
| `retrieve_bike_knowledge` | read | `query` (≤ 500) | `{queries, appliedFilters, candidateMotorbikeIds, snippets[≤6]}` |
| `record_preference` | write | `attribute`, `value`, `firmness` | the normalised triple |
| `flag_unknown_bike` | write | `name` | `{name, status: queued\|already_known}` |
| `present_recommendations` | write | ≤ 4 × `{id or name, rationale ≤300, matchedPreferences ≤6}` | `{presented[], skipped[], message}` |

Notes that matter:

- **`licence_fit_check` knows only A2 and A** — no A1. A2 limits are imported
  from `product_service` (35 kW, 0.2 kW/kg), so the tool and the catalogue
  filter can never disagree.
- **`cost_estimator` reads a versioned coefficient table** (`cost_data.py`,
  Germany/EUR, `COEFFICIENTS_VERSION`) — no config, no external API. A line item
  whose input is unverified is *omitted* and the gap is named in `assumptions`;
  the last assumption is always the "not a quote" disclaimer. It prices from
  verified `msrp_eur`, falling back to the price-band midpoint;
  [used prices](used-prices.md) are **not** wired in.
- **`retrieve_bike_knowledge` is the only consumer of the RAG pipeline.** Its
  snippets minus `text` become the message's `sources[]`.
- **`flag_unknown_bike` dedupes by slug only**, so a differently-spelled name
  creates a second backlog row. Known boundary.
- **`present_recommendations` snapshots** name, image URL and key specs at write
  time, so a card keeps rendering after the catalogue changes.

CLI: `app tools run <tool> --args '<json>'` (prints the model view).

## The advisor loop

`llm/agents/advisor.py::run_advisor_turn(session, chat, *, model=None) ->
AdvisorResult(body, tool_calls, sources, recommendations)`.

Context is the system prompt (`advisor_system.md`, rendered with `is_opening`
and the fenced active preferences) plus the full timeline as Human/AI messages —
**bodies only**. Past tool traffic is never replayed, and there is no rolling
summary.

One round = one tool-bound `ainvoke` plus sequential execution of every call it
returned. After `AGENT_MAX_TOOL_STEPS` (8) rounds the loop appends a wrap-up
`SystemMessage` and makes one final call with tools unbound, so a turn always
ends in prose. The whole turn runs under
`asyncio.timeout(AGENT_TIMEOUT_SECONDS)` (120 s). A failing tool, an unknown
tool name or a validation error becomes an error `ToolMessage` and the loop
continues; only a gateway failure, the timeout or an empty answer ends a turn.

`chat_response_service.generate` is a thin wrapper that persists the result and
raises `EmptyAnswerError` on a blank body.

### Prompt

`advisor_system.md` pins: domain scope and refusal; the interview order
(experience → licence → use case → budget → physique → preferences); "steer,
never insist"; record preferences while learning them; ids and names are copied
from tool results, never recalled from memory; a named model is looked up rather
than judged; budget stays out of the first `catalogue_search`; `totalCount: 0`
means retry without the least essential filter *and say so*; the untrusted-data
fence rule; and the opening-vs-continue branch. The prompt suggests presenting
up to three models; the code cap is four.

## Configuration

| Key | Default | Meaning |
|---|---|---|
| `ADVISOR_MODEL` | `openai/gpt-4.1-mini` | Consultation model |
| `CHAT_MODEL` | `openai/gpt-4.1-mini` | Query translation, extraction, utilities |
| `RRF_K` | 60 | Fusion constant, both passes |
| `RETRIEVAL_CANDIDATES_PER_LEG` | 50 | Per-leg candidate cap |
| `AGENT_MAX_TOOL_STEPS` | 8 | Tool rounds before wrap-up |
| `AGENT_TIMEOUT_SECONDS` | 120 | Whole-turn budget |

Client-side: chat requests time out at 60 s, embeddings at 30 s, both with
`max_retries = 2`.
