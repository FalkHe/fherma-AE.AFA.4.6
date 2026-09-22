---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
url: –
---
# Review: Sprint 03 — the corpus is ingested, and says what it cost

## What changed
The rulebook is now loaded for real: one command fetches the stored SRD 5.1, embeds all 1750 passages through the LLM gateway and stores them, then reports source version, size, passage count, tokens and the cost in USD. The status command afterwards reports the passage count, the embedding model and the time of the import instead of an empty corpus. No two passages can carry the same citation, enforced by the database.

## How to check it
- Run the ingest command with a real gateway key: it prints the report, and the status command then shows 1750 rules, the embedding model and the import time, exiting normally.
- Every stored passage carries its heading path, position, text, token count and the model used; no citation appears twice.
- A gateway failure during embedding writes nothing: the corpus stays as it was, and the stored source file is restored to its previous content.
- Ingestion is reachable from the command line only; no screen or API endpoint touches the rules table.

## Heads-up
- The implementation was ported from an earlier, never-reviewed attempt on the server (16 September) rather than written fresh, as requested. Tests are minimal; the live import is the proof.
- A repeat import already replaces the corpus wholesale in one transaction, so the next sprint may be a verification pass rather than new work.

Brief: docs/intents/004-srd-knowledge-base/sprints/03-corpus-ingested/brief.md

## Verdict
