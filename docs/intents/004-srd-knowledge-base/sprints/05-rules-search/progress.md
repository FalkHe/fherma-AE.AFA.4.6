---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: done
---
# Progress: Sprint 05 — rules search

| WI | Status | Note |
|---|---|---|
| 1 | done | `search_rules`, `RuleMatch`, `DEFAULT_LIMIT`, `app srd search`, heading-trail embedding in `ingest`, README; re-ingest 13:04 UTC (USD 0.0106); live: "how does half cover work" → Combat › Cover #0 (0.515) first; "what happens when a creature is frightened" → Conditions › … › Frightened (0.389) first; "what does fire bolt do" --limit 3 → Spell Descriptions › … › Fire Bolt (0.486) first; stored source unchanged; commits 9069fe9 841beb6 |

Status: `open | running | done | failed`

## Issues
- The brief predates the `## Task` template section; its `## Outcome` matches backlog row 05, so no `/fhit:backlog` repair was run.
- Architect found that main embeds each passage body without its heading, so a spell's name lives only in `heading_path` and "fire bolt" ranks around 47th. Sprint lead decided to embed the heading trail with the body in `ingest` and re-ingest once (about one cent): it is the least effort way to make AC4's spell question pass and the number sprint 06 measures should be measured on the final embedding. Stored `text` stays the body, so the reported token count understates by roughly 5 %.
- `score` is the raw cosine distance (lower is closer), not the stale branch's similarity, because sprint 06's approved brief thresholds a distance.
- Branch carries `-r2`; `origin/sprint/004-05-rules-search` is the stale 2026-09-16 chain, used as porting reference.
- `glab` is signed in as `f4lkh3`; MR assignee is set to `st3ll4` explicitly.

## Backlog proposals
- Heading paths nest wrongly in places: `Adventuring › Conditions › Blinded › Frightened` and `Spell Lists › Spell Descriptions › Acid Arrow › Fire Bolt` — the first sibling heading becomes the parent of the rest, probably because the source raises the level for the first entry only or the chunker mishandles equal-level siblings after a deeper heading. The citation still points at the right passage but reads oddly; worth a chunker fix before citations are shown to players.
- Runner-up matches are lexical look-alikes (Half-Dragon, Half-Elf for "half cover"); sprint 06's floor will decide how many of those survive.

## Gates
Lint, backend suite (1021 passed), database-marked suite (151 passed) and frontend suite (65) pass.

## Verify
Round 1: approve — AC1–AC6 and D1/D2/D4 pass on the verifier's own live queries. Nit carried: README's search paragraph says "any other SrdError" while the command catches `SrdVectorWidthError` specifically. Approval posted with the human's glab token, as before.
