---
author: fhit:architect
owner: agent
created: 2026-09-22
---
# Research: sprint 004-07 — citation heading levels

## Facts

- `_parse_sections` cuts the open-heading stack by depth, not by level:
  `stack = stack[: level - 1]` then `append` (`backend/app/modules/srd/service.py:170-172`).
  The source skips levels — `## Spell Descriptions` at
  `backend/content/srd/v1/SRD_CC_v5.1.md:11725` is followed by `#### Acid Arrow`
  (`:11727`) and `#### Acid Splash` (`:11745`) — so every later sibling nests under
  the first one.
- Measured against the real source (chunker run in `app-cli`, level-aware stack as
  reference): 479 of 1736 sections and 481 of 1750 chunks carry a wrong citation.
  By prefix: 318 `Spell Lists › Spell Descriptions › Acid Arrow`, 96
  `… › Creature Descriptions › Ape`, 31 `Classes › Eldritch Invocations ›
  Agonizing Blast`, 20 `… › Nonplayer Character Descriptions › Acolyte`, 14
  `Adventuring › Conditions › Blinded`. Two of these wrong paths are printed as
  measurement evidence in `backend/app/modules/srd/README.md:102-103`.
- `_HEADING_RE` stops at four hashes (`service.py:39`). Heading histogram of the
  source: 17 `#`, 106 `##`, 626 `###`, 987 `####`, 362 `#####`. Of the 362 `#####`,
  315 are `Actions`, 30 `Legendary Actions`, 12 `Reactions` — i.e. sub-blocks of a
  monster stat block (`#### Aboleth` → `##### Actions`), not standalone rules.
- Anchor ids exist only on 16 of 17 `#` and all 106 `##` headings; 1 of 626 `###`,
  1 of 987 `####`, 0 of 362 `#####`. An anchor-based citation path is not
  constructible from this source.
- Collision check, run over the real source: **zero** duplicate
  `(heading_path, ordinal)` keys under the current parser, under a level-aware
  stack, and under a level-aware stack that also reads `#####`. The unique
  constraint (`backend/alembic/versions/0009_srd_rules_unique_citation.py:21-25`)
  cannot fire for any of the options.
- Chunk counts (real source, real `_split_body`/tiktoken): current 1750 chunks /
  507,719 tokens; level-aware stack alone 1750 / 507,719 (paths change, counts do
  not); level-aware plus `#####` 2095 chunks / 504,687 tokens, and the number of
  sections that must be split for size drops from 64 to 47.
- The heading trail is part of what is embedded (`service.py:356`), so any path
  change requires a full re-ingest; at `openai/text-embedding-3-small`
  (`backend/app/core/settings.py:20`) ~0.5M tokens is roughly one US cent.
- `RELEVANCE_FLOOR = 0.60` (`service.py:417`) and its 11-query table
  (`README.md:89-116`) were measured against the current corpus.

## Options

| Option | Pro | Con |
|---|---|---|
| A: level-aware stack (pop while top level ≥ current), regex unchanged | Fixes all 481 wrong citations; no chunk-count, cost or granularity change; smallest diff | Monster `Actions`/`Reactions` stay folded into the parent stat block |
| B: A + regex extended to `#####` | Also cites stat-block sub-parts; 17 fewer oversized-section splits | +345 chunks (+20%) and 345 more rows; splits a stat block from its actions, so "what does an aboleth do" can return the table without the attacks |
| C: anchor-id based paths | Stable across heading edits | Impossible here: 2 of 1975 `###`/`####`/`#####` headings carry an anchor |

Recommendation: take A — it removes every wrong citation at zero cost to chunking,
cost or retrieval shape, and leaves the `#####` granularity question as a separate,
measurable decision rather than bundling an unproven retrieval change into a bug fix.

## Work items

- WI1 (backend-python): make `_parse_sections` pop the stack by heading level, keep
  the regex at `#{1,4}`, extend `backend/tests/srd/test_chunk_source.py` with a
  skip-level fixture (`# A` → `## B` → `#### C` → `#### D`) asserting `C` and `D` are
  siblings, and update `backend/app/modules/srd/README.md` (chunking paragraph, and
  the two wrong citations in the floor table once WI2 has re-measured them).
- WI2 (backend-python, after WI1): re-ingest (`docker compose run --rm app-cli app
  srd ingest`), re-run the 11 README queries, and record the new best-distance table
  plus the new rule count; keep `RELEVANCE_FLOOR = 0.60` if the in/out gap still
  brackets it, otherwise report the new gap and stop rather than repinning silently.

## Interfaces

WI1 → WI2: `service.chunk_source` keeps its signature and `RuleChunk` shape
(`schemas.py`); only `heading_path` values change. WI2 changes no code except, if
the measurement demands it, the `RELEVANCE_FLOOR` literal at `service.py:417` with
its comment block. Both work items write to `README.md` — WI1 owns the chunking
paragraph, WI2 owns the "Relevance floor" section.

## Open questions

- Should a monster's `Actions` / `Legendary Actions` / `Reactions` be citable in
  their own right, or stay part of the monster's single passage? A player sees the
  difference in what a rules answer quotes: the whole stat block, or just the attacks.
  Not decidable from the code — needs a decision before option B is ever taken.
- The corpus is re-embedded as part of this fix; if the re-measurement moves the
  relevance floor, some questions that were answered before will answer
  "no relevant rule" and vice versa. Is a floor change inside this sprint acceptable,
  or must it come back as its own decision?
