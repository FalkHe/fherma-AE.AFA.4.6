---
author: sprint
owner: agent
created: 2026-09-16
updated: 2026-09-16
stage: draft
---
# Progress: Sprint 06

| WI | Status | Note |
|---|---|---|
| 1 | done | resolver + grammar + numeric versions, 20 tests |
| 2 | done | app prompt show, exits 0/2/3, 8 tests |
| 3 | done | seed + guard, proven red on a bad path and a non-.md file |
| 4 | done | model.md layout corrected, closes register entry :333 |
| qa | done | 32 acceptance tests, AC1-AC5 green |

Status: `open | running | done | failed`

## Issues
- First sprint of this intent touching no provider: no network, no `classify()`, no retry.
- The seed pre-creates phase 8's `modules/game/` as a prompts-only directory with no Python in it. The alternative was putting a prompt in a module that owns none. A reviewer can move the file without touching the resolver.

- Sprint lead exercised the real CLI against the seed (every WI test uses `tmp_path`): stdout is byte-identical to the file (`diff -` passes); unknown id exits 3, malformed exits 2; `../../etc/passwd` and `game/../game/system/smoke` are rejected as **invalid**, not not-found; `--version v9` when only v1 exists fails rather than falling back (D5).
- WI1 and qa both reported inflated suite totals (1329 and "1400+") against a real 482. Sub-agent test counts are worth re-measuring rather than quoting.

## Backlog proposals

## Verify
Round 1: **changes-requested** (note #86). AC4 failed: `_SEGMENT`/`VERSION_PATTERN` anchored with `$`, which in Python matches before a trailing newline — so `game/system/smoke\n` passed the grammar, built a `Path`, hit the filesystem and failed as NOT_FOUND/exit 3, defeating the design's "refused before any Path is built" claim. AC1 partial: `read_text()` translated CRLF to LF, so a prompt was not verbatim. Plus `list_versions` did not validate `capability`.
Round 2: all three fixed (`re.fullmatch`, `read_bytes().decode()`, capability validated), each proven red-then-green; 486 passed. Lead re-verified live via CliRunner: both trailing-newline cases now exit 2 as invalid.
