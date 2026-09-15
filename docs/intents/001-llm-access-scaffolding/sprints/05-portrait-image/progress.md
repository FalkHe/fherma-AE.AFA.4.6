---
author: sprint
owner: agent
created: 2026-09-15
updated: 2026-09-15
stage: done
---
# Progress: Sprint 05

| WI | Status | Note |
|---|---|---|
| 1 | done | ImageResult + generate_image, classify/retry reused, 23 tests |
| 2 | done | app llm image + _usage_text extraction, 12 tests |
| qa | done | AC3-AC5 green, 17 tests; lead committed them after its turn limit |

Status: `open | running | done | failed`

## Issues
- Research made one live image call to establish the response shape (~$0.067). Third sprint running where the intent research's transport assumption was wrong and re-verifying avoided building a parallel error path.
- `usage.cost` absent reads back as `Unset()`, not `None` — it would crash `_cost_text` at `round(Unset(), 6)`.

- AC1/AC2/AC3 hand-run live: 768x1376 PNG, a genuine portrait matching the prompt, `cost: $0.067209`, and the logged URL `https://openrouter.ai/api/v1/images` with `google/gemini-3.1-flash-image` — OpenRouter, never Google's own API (D1).
- qa hit its 40-turn limit for the fifth sprint running, this time with the work finished but uncommitted.

## Backlog proposals
- **Portrait economics, for phase 7:** ~$0.067 and ~1.7 MB per portrait at the model's defaults. A character-creation flow that regenerates freely is materially expensive, and 1.7 MB per stored portrait adds up. `resolution` / `output_format` exist on `images.generate` if either needs tuning; choosing them is out of scope here.

## Verify
Round 1: approved — AC1–AC5 pass, D1/D3/D4 honoured, no scope creep. Gates clean, 412 passed in 3.84s.
AC5 mutation-tested by the verifier: placeholder returns injected into the empty-`data`, `classify()` and base64-decode paths turned 7 / 24 / 2 tests red respectively; tree restored and re-verified clean. D1 asserted on the real request host inside the mock transport, with the logged URL derived from `get_server_details()` rather than a literal.
One non-blocking gap closed in-round: `b64_json: ""` decoded to zero bytes and exited 0 with a 0-byte file — success reported for an unusable result. Now `LlmMalformedError`, verified red-then-green.
Approval withheld — author and reviewer are the same account (note #79).
