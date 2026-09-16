---
author: fhit:architect
owner: agent
created: 2026-09-16
updated: 2026-09-16
---
# Research: sprint 06 — relevance floor

## Facts

**Measurement.** Live corpus (2,132 rows), real gateway, `search_rules(db, q, limit=3)`;
`score = 1 − cosine_distance` (`service.py:556`). Every in-corpus top match was correct.

| # | kind | in-corpus query | top |
|---|---|---|---|
| I1 | condition | what does the poisoned condition do | 0.599 |
| I2 | combat | how does grappling work | 0.638 |
| I3 | cover | how does half cover work | **0.485** |
| I4 | spell | what does fire bolt do | 0.514 |
| I5 | class | how does a rogue's sneak attack work | 0.740 |
| I6 | monster | how much damage does an owlbear do with its claws | 0.704 |
| I7 | equipment | how much does plate armor cost and what AC does it give | 0.620 |
| I8 | skill | how do I hide and make a stealth check | 0.661 |
| I9 | rest | what do I get back when I take a long rest | 0.629 |
| I10 | combat | what is an opportunity attack and when can I make one | 0.649 |
| I11 | spellcasting | how does concentration on a spell work | 0.692 |
| I12 | death | what happens when I drop to 0 hit points | 0.772 |

| # | kind | out-of-corpus query | top |
|---|---|---|---|
| O1 | sci-fi | how do I reload a plasma rifle | 0.295 |
| O2 | non-SRD subclass | what does the Hexblade warlock patron give me | **0.631** |
| O3 | non-SRD spell | how does the spell Silvery Barbs work | 0.468 |
| O4 | deities | which deities are worshipped in the Forgotten Realms | 0.504 |
| O5 | non-SRD subclass | how does the Bladesinging wizard tradition work | 0.484 |
| O6 | modern | what interest rate on a thirty year mortgage | 0.186 |
| O7 | other system | how do I spend fate points in Fate Core | 0.482 |
| O8 | other system | how does the Pathfinder three action economy work | 0.452 |
| O9 | jargon, no rule | how much gold to bribe a city guard captain | 0.329 |
| O10 | jargon, no rule | how many XP do I award for good roleplaying | 0.538 |
| O11 | modern | what is the best way to sharpen a kitchen knife | 0.371 |

**The groups overlap — no clean floor exists.** Lowest in-corpus 0.485 (I3), highest out-of-corpus
0.631 (O2): the gap is **negative, −0.146**. Four out-of-corpus queries outscore a question the SRD
answers, each a *near miss* landing on a generic feature it does have — Otherworldly Patron,
Experience Points, the Norse pantheon, Arcane Tradition.

**What a floor still buys.** The widest band holding no in-corpus query is 0.371 → 0.452.
**Recommend `RELEVANCE_FLOOR = 0.40`**: **0.085** of margin below the lowest kept score (I3),
**0.029** above the highest rejected one (O11). It keeps all twelve in-corpus queries and rejects the
four topically alien ones (O1, O6, O9, O11) — AC1 and AC2 both hold. 0.45 buys only O8 for 0.002 of
margin; 0.35 loses O11. I3's ranks 2–5 are noise (0.356, 0.310), so "half cover" now returns one
passage, the right one, not five.

**Filter after the query, never in SQL.** `EXPLAIN (ANALYZE)`, live corpus, pgvector 0.8.6 server /
`pgvector` 0.5.0 (`backend/uv.lock:678`, local). `ORDER BY embedding <=> $1 LIMIT 5` → `Index Scan
using ix_srd_rules_embedding`, 0.996 ms. Adding `WHERE embedding <=> $1 < 0.55` → `Seq Scan` +
`Sort`, `Rows Removed by Filter: 2082`, 8.475 ms: the index is lost. The same filter *outside* that
subquery keeps `Index Scan`, 0.367 ms. So `service.py:557` stays as it is; the floor applies in
Python to the rows it returned.

**Floor and limit.** Rows arrive distance-ordered, so the kept set is a prefix: cut at the first row
below the floor. `DEFAULT_LIMIT = 5` (`service.py:522`) becomes a cap, not a count, with no
re-fetch to refill it.

**Exit codes (AC5).** An empty corpus already exits **1** with `EMPTY_CORPUS_MESSAGE` on **stderr**
(`commands.py:216`). "No relevant rule" is no failure: one **stdout** line, exit **0** — different
code, stream and wording, no new exception type.

**Offline tests.** `test_search_service.py:74` already scores synthetic basis vectors against the
migrated table via `srd_db` — exactly 1.0, 0.707, 0.0 — with `FakeGateway` (`:57`) as the query
vector; no real embedding call happens. 0.40 sits between 0.0 and 0.707, and an all-orthogonal
corpus proves the empty result.

## Work items

- **WI1 service**: `RELEVANCE_FLOOR` beside `DEFAULT_LIMIT`, applied in `search_rules` after the
  query; fix the docstrings saying no floor applies. Tests: below-floor absent, at-floor kept,
  all-below → `[]`, no `WHERE` on distance.
- **WI2 command**: on an empty result, `search` prints one "no relevant rule" stdout line, exit 0.
  Tests: that case; empty corpus still exit 1 on stderr, stdout empty; non-empty unchanged.
- **WI3 docs**: `README.md` records the floor, the measured queries and scores, the overlap finding
  and the exit codes (AC3).

## Interfaces

- `service.RELEVANCE_FLOOR: float = 0.40` — module constant; no setting, no flag.
- `search_rules(db, query, *, limit=DEFAULT_LIMIT) -> list[RuleMatch]` — unchanged signature; every
  match has `score >= RELEVANCE_FLOOR`; the list may be short or empty; `SrdCorpusEmptyError` first.
- `commands.NO_RELEVANT_RULE_MESSAGE = "no relevant rule found in the SRD for that question."` —
  stdout, exit 0, only when `matches == []`.

## Open questions

**Product-visible.** The floor does less than D7 sounds like it promises: it rejects questions the
SRD has no topic for, but not D&D-flavoured questions about material the SRD omits — a Hexblade
patron, Forgotten Realms deities, XP for roleplaying all outscore half cover and still return
plausible wrong rules. Accept only the alien-question half of D7 here, leaving the near-miss half to
phase 8's prompt?

**Internal.** None.
