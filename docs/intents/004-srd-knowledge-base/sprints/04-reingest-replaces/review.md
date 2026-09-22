---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
url: –
---
# Review: Sprint 04 — a second ingest replaces the corpus instead of growing it

## What changed
Nothing in how the product behaves: the import delivered in the previous sprint already replaces the whole rulebook in one step and keeps the old one if anything goes wrong. This sprint proves it. A second live import was run today, and automated checks now pin the behaviour so it cannot regress silently.

## How to check it
- Run the import twice: the status command reports the same 1750 rules both times, with a later import time after the second run. Today's runs: 10:09 UTC, then 12:30 UTC, cost about one cent.
- No passage is stored twice: every heading path and position pair is unique, enforced by the database, and checked after two runs.
- An import that fails after some passages were already embedded writes nothing; the earlier rulebook and its stored source text stay exactly as they were.
- A changed source text changes the passage count and the stored file's diff together, so the rulebook and the repository never disagree.
- The replacement happens in one transaction; there is no moment in which the status command would see a half-loaded rulebook.

## Heads-up
- No product code changed; the work is tests, one documentation note and the live proof.
- If a future source ever contained two sections with an identical heading trail, the import would refuse it and keep the previous rulebook. The current source has none. Noted as a backlog proposal.

Brief: docs/intents/004-srd-knowledge-base/sprints/04-reingest-replaces/brief.md

## Verdict
