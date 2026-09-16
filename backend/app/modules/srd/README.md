# srd

Owns the SRD 5.1 rules knowledge base — the citable passages and their
embeddings the DM agent retrieves rules from. Self-contained: nothing outside
this module reaches the corpus directly (D1).

## Owns

- The `srd_rules` table (`models.py`): one citable passage per row —
  `source_version`, `heading_path`, `ordinal`, `text`, `token_count`,
  `embedding_model`, `embedding` (`VECTOR(EMBEDDING_WIDTH)`, `EMBEDDING_WIDTH
  = 1536`) — indexed by `ix_srd_rules_embedding`, an HNSW `vector_cosine_ops`
  index for nearest-neighbour lookup, and constrained unique on
  `(source_version, heading_path, ordinal)` — the database itself refuses a
  duplicate citation, independent of `chunk_source`'s own numbering.
- `RuleChunk` / `RuleMatch` / `IngestReport` (`schemas.py`): a `RuleChunk` is
  one citable passage `service.chunk_source` produced — `heading_path`,
  `ordinal`, `text`, `token_count`; `text` is body only, but `token_count`
  covers what is actually sent to the embedder — the heading trail joined to
  the body — so it stays honest even though the stored/cited `text` never
  carries the heading a second time. A `RuleMatch` is one passage
  `service.search_rules` returned — the same `heading_path`/`ordinal`/`text`
  plus `score` (`1 - cosine_distance`, higher is closer), best match first.
  An `IngestReport` is what one `app srd ingest` run did or would do —
  source version, stored byte count, chunk count, total token count,
  `cost_usd` and `cost_complete`. `cost_usd` is `None` under `--dry-run` (no
  embedding call) or when a real run priced no batch at all; otherwise it is
  the sum of every batch the gateway did price, and `cost_complete` is
  `False` when that was only some of them — a known lower bound rather than
  the true total.
- `SrdError` / `SrdCorpusEmptyError` / `SrdVectorWidthError` / `SrdSourceError`
  (`errors.py`).
- The `vector` extension and the `srd_rules` table/index migration
  (`alembic/versions/0002_srd_rules.py`), plus the
  `(source_version, heading_path, ordinal)` unique constraint
  (`alembic/versions/0003_srd_rules_unique_citation.py`).

## Surface

- `app srd status` (`commands.py`): reports rule count, source version,
  embedding model and ingest time on stdout; exits 1 with a stderr line
  naming 0 rules and `app srd ingest` when the corpus is empty, or naming
  both widths on a vector-width mismatch.
- `app srd ingest --dry-run` (`commands.py`): fetches the source document,
  stores it and splits it into citable chunks, then prints the stored
  path, byte count, chunk count, total token count and a sample of heading
  paths — fetch + store + chunk only, no database and no embedding call.
- `app srd ingest` (no flag, `commands.py`): runs `service.ingest` for
  real — one progress line per embed batch, then the report (source
  version, bytes, chunk count, token count, cost). A gateway failure
  (`LlmError`) or a source/vector-width failure (`SrdError`) prints one
  stderr line and exits 1, never a traceback.
- `app srd search QUERY [--limit N]` (`commands.py`): runs
  `service.search_rules`, then prints each `RuleMatch` numbered, best
  first — its heading trail, ordinal and score on one line, the passage
  text indented below. `--limit` caps how many come back, defaulting to
  `service.DEFAULT_LIMIT` when omitted; a non-positive `--limit` is
  rejected by hand with one stderr line before any query runs. Two
  outcomes both look like "nothing to show" but are told apart by exit
  code: nothing scoring at or above `RELEVANCE_FLOOR` prints `no relevant
  rule found for this query` to stdout and exits 0 — a successful search
  that found nothing, not a failure; an empty corpus
  (`SrdCorpusEmptyError`) prints the same empty-corpus message `status`
  uses, to stderr, and exits 1. Any other `SrdError` or a gateway failure
  (`LlmError`) prints one stderr line and exits 1, never a traceback.
- `service.ingest(db, *, version, on_batch)` (`service.py`): fetches,
  stores, chunks, embeds in `EMBED_BATCH_SIZE`-sized batches and replaces
  `srd_rules` wholesale in one transaction opened only after every vector
  is in hand; `on_batch(chunks_done, chunks_total)` fires after each batch
  for a caller's progress reporting — the service itself never prints. Each
  chunk is embedded as its heading trail joined to its body, not the body
  alone — a passage's own name (e.g. a spell) often lives only in its
  heading — while the stored row's `text` stays body-only, what a citation
  quotes back. Any failure after the new source file replaces the old
  one — chunking, embedding or the write — restores the previous file
  byte-for-byte (or removes it entirely when there was none) before
  re-raising, so the stored file and the corpus can never disagree; the
  restore itself only ever swallows its own filesystem error, never the
  failure that triggered it.
- `service.search_rules(db, query, *, limit=DEFAULT_LIMIT)` (`service.py`):
  embeds `query` through the shared gateway, orders `srd_rules` by cosine
  distance and takes the closest `limit` rows, then drops every one
  scoring below `RELEVANCE_FLOOR` before returning the rest as
  `RuleMatch`es, best first (see "Relevance floor" below). `require_corpus`
  runs first, so an empty corpus raises `SrdCorpusEmptyError` before
  `query` ever reaches the gateway.
- `service.fetch_source()` downloads `SOURCE_URL` and stores it at
  `SRD_ROOT/<version>/SOURCE_FILENAME`, overwriting an existing copy in
  place; a non-200 response, a timeout/connection failure or an empty body
  raise `SrdSourceError` and leave a previously stored file untouched (the
  download lands in a temporary file first, then is moved into place).
- `service.count_tokens(text)` / `service.chunk_source(path)`: splits a
  stored document into one `RuleChunk` per heading section, further
  splitting an oversized section on token boundaries with overlap so a
  citation at a split still reads in context (`MAX_CHUNK_TOKENS`,
  `CHUNK_OVERLAP_TOKENS`); a heading with no body text yields no chunk.
  `ordinal` numbers passages per heading trail across the whole document,
  not per markdown section, so two headings that collapse to the same
  anchor-free trail continue one shared sequence instead of both starting
  at 0.
- `backend/content/srd/v1/` vendors the rules source (`SRD_CC_v5.1.md`) and
  its licence (`LICENSE.md`) that `fetch_source`/`chunk_source` read.

## Relevance floor

- `RELEVANCE_FLOOR = 0.43` (`service.py`) is a pinned module constant, not
  a setting — it carries no field on `Settings` and is never read from the
  environment, because it moves with the pinned embedding model
  (`EMBEDDING_MODEL`), not with a deployment; a model swap re-measures it.
  `search_rules` applies it in Python, after the query is already ordered
  and `LIMIT`-applied, never as a SQL `WHERE` on the distance: `EXPLAIN
  ANALYZE` on the real corpus gives `Index Scan` at 0.996 ms for the query
  as it stands; adding a `WHERE` on the distance drops the planner to
  `Seq Scan` + `Sort` at 8.475 ms, because a condition on the ordering
  expression itself defeats the reason to reach for the HNSW index at
  all, while filtering after the same ordered, limited query keeps it at
  0.367 ms. Consequence: `DEFAULT_LIMIT` (and any `--limit`) caps what a
  search *may* return, not a count of what it *will* — a below-floor row
  is dropped outright, so the result can be shorter than `limit`,
  including empty.
- **How 0.43 was chosen**: twelve in-corpus and eleven out-of-corpus
  questions, each the *exact* string measured — reproduce any row with
  `docker compose run --rm app-cli app srd search "<query>" --limit 1`
  against the real ingested corpus (`openai/text-embedding-3-small`,
  2,132 rules). For a query whose top score falls below the floor, that
  exact command prints `no relevant rule found for this query` rather
  than a score — the score and heading below are the same underlying
  nearest-neighbour result, read before `RELEVANCE_FLOOR` drops it.

  In-corpus (every one the correct passage):

  | query | top score | top match |
  |---|---|---|
  | What happens when a creature is poisoned? | 0.661 | Adventuring › Conditions › Blinded › Poisoned |
  | How does grappling work in combat? | 0.716 | Combat › Making an Attack › Melee Attacks › Grappling |
  | How does half cover work? | 0.531 | Combat › Cover |
  | How much damage does fire bolt deal? | 0.526 | Spell Lists › Spell Descriptions › Acid Arrow › Fire Bolt |
  | How does a rogue's sneak attack work? | 0.740 | Classes › Rogue › Sneak Attack |
  | How much damage does an owlbear's claw attack do? | 0.722 | Monsters › Monster Descriptions › Uncategorized › Owlbear › Actions |
  | How much does plate armor cost and what AC does it give? | 0.661 | Equipment › Armor |
  | How do I make a hide check to stay stealthy? | 0.622 | Combat › Actions in Combat › Hide |
  | How much do I recover from a long rest? | 0.597 | Adventuring › Resting › Long Rest |
  | What is an opportunity attack? | 0.567 | Combat › Making an Attack › Melee Attacks › Opportunity Attacks |
  | How does concentration work for spells? | 0.697 | Spellcasting › Casting a Spell › Duration › Concentration |
  | What happens when I drop to 0 hit points? | 0.797 | Combat › Damage and Healing › Dropping to 0 Hit Points |

  Out-of-corpus:

  | query | top score | top match |
  |---|---|---|
  | How do I reload a plasma rifle? | 0.296 | Classes › Eldritch Invocations › Agonizing Blast › Thief of Five Fates |
  | What is a Hexblade warlock's patron? | 0.668 | Classes › Otherworldly Patrons |
  | What does the spell Silvery Barbs do? | 0.456 | Spell Lists › Spell Descriptions › Acid Arrow › Antilife Shell |
  | Who are the deities of the Forgotten Realms? | 0.509 | Pantheons › The Celtic Pantheon |
  | How does Bladesinging work for a wizard? | 0.484 | Classes › Wizard › Class Features |
  | What's a good interest rate for a thirty-year mortgage? | 0.180 | Beyond 1st Level › Character Advancement |
  | How do fate points work in Fate Core? | 0.489 | Classes › Otherworldly Patrons › The Fiend › Dark One's Own Luck |
  | How does action economy work in Pathfinder? | 0.538 | Combat › Actions in Combat |
  | How do I bribe a city guard? | 0.350 | Equipment › Services |
  | How much XP do I get for good roleplaying? | 0.512 | Beyond 1st Level › Character Advancement |
  | How do I sharpen a kitchen knife? | 0.397 | Magic Items › Magic Item Descriptions › Sword of Sharpness |

- **The finding**: the two groups overlap. The weakest in-corpus question
  scores 0.526 (fire bolt); the strongest out-of-corpus question scores
  0.668 (Hexblade warlock's patron) — higher than *five* of the twelve
  in-corpus questions, because it is a near miss landing on a real,
  generic SRD feature (`Otherworldly Patrons`). Seven of the eleven
  out-of-corpus questions score above the floor outright, for the same
  reason (a real Otherworldly Patron sub-feature, the Character
  Advancement/XP table, a real pantheon, the Wizard's own class-features
  section). Sorted, the out-of-corpus top scores are 0.180, 0.296, 0.350,
  0.397, 0.456, 0.484, 0.489, 0.509, 0.512, 0.538, 0.668; the widest band
  below the lowest in-corpus score (0.526) containing no question at all
  — in either group — is 0.397 to 0.456. `0.43` sits in the middle of
  that band: 0.033 above the highest-scoring rejected question (sharpen a
  kitchen knife, 0.397) and 0.096 below the lowest-scoring kept one (fire
  bolt, 0.526). It rejects the same four out-of-corpus questions 0.40
  did — nothing about which questions pass or fail changes — but a small
  rewording of any of the 23 measured questions is far less likely to
  flip the outcome now.
- **What it does not protect against**: a D&D-flavoured question about
  material the SRD simply omits still returns a plausible but wrong rule
  above the floor — a similarity score cannot tell "close topic, wrong
  rule" apart from "right rule", and this measurement shows that failure
  mode is the common case, not the exception: most alien-but-D&D-shaped
  questions scored above the floor. Known, recorded limit, not something
  engineered around here.

## Notes

- This work includes material taken from the System Reference Document 5.1
  ("SRD 5.1") by Wizards of the Coast LLC and available at
  https://dnd.wizards.com/resources/systems-reference-document. The SRD 5.1
  is licensed under the Creative Commons Attribution 4.0 International
  License available at https://creativecommons.org/licenses/by/4.0/legalcode
  (D6).
- `srd_rules` is owned by nobody and replaced wholesale on re-ingest — no
  row-level ownership or partial update (`module-structure.md` §2).
