---
author: fhit:architect
owner: human
created: 2026-09-15
stage: approved
---
# Sprint 02: the SRD arrives in the repo and is split into citable chunks

## Outcome
`app srd ingest --dry-run` fetches SRD 5.1 from the CC-BY source into `backend/content/srd/v1/`, reports
how many citable chunks it would embed, and a changed upstream shows up as a git diff.

## Acceptance criteria
- AC1: `docker compose run --rm app-cli app srd ingest --dry-run` writes `backend/content/srd/v1/SRD_CC_v5.1.md` and prints the stored path and byte count.
- AC2: the same run prints the chunk count, the total token count and a sample of heading paths (e.g. `Combat › Cover › Half Cover`) — each chunk carries a reference good enough to cite (← D4).
- AC3: re-running overwrites the stored file, so `git diff` is the only place an upstream change appears (← D3); an unchanged upstream leaves the tree clean.
- AC4: no chunk exceeds the embedding model's input window; a larger section is split with overlap, keeping its parent heading path and gaining an ordinal.
- AC5: an unreachable or unparseable source exits non-zero with `SrdSourceError`'s message, not a traceback, and leaves the stored file untouched.
- AC6: `backend/content/srd/v1/LICENSE.md` holds the CC-BY-4.0 attribution sentence and the repository `README.md` states it too (← D6).

## Decisions
← D2, D3, D4, D6

## Assumptions
- `--dry-run` is fetch + store + chunk + report, no database and no embedding call, so D3's first half is mergeable while `embed_texts` is open; 03 is the same command without the flag.
- The fetch uses the HTTP client already in the dependency tree; `SOURCE_URL` and `SOURCE_VERSION` are module constants, not settings.
- Heading-first chunking with a token split of oversized sections, counted by `tiktoken`; `SRD_ROOT` is repointable via `monkeypatch.setattr` as `CONTENT_ROOT` is, so tests chunk a fixture, never the network.

## Out of scope
Embedding, storing rows, searching (03–06) · the player-facing citation display (later stage, ← D4/D6).
