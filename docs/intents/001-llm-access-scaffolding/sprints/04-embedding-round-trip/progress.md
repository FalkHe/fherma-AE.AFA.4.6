---
author: sprint
owner: agent
created: 2026-09-15
updated: 2026-09-15
stage: done
---
# Progress: Sprint 04

| WI | Status | Note |
|---|---|---|
| 1 | done | 2 settings + conftest pins, 2 tests, suite 307 |
| 2 | done | embed_texts + EmbeddingResult, 23 tests, red-first verified |
| 3 | done | app llm embed + two byte-identical refactors, 9 tests |
| qa | done | AC3-AC5 green, 9 tests incl. shuffled-index and no-dimensions |

Status: `open | running | done | failed`

## Issues
- Branched off `sprint/001-03-quiet-retry`, not `main`: !6 was still open and both sprints edit `service.py`. Embeddings therefore inherit D6's retry. **!6 must merge before this sprint's MR.** It did — but GitLab **squash-merges**, so sprint 03's ten commits are in `main` under one new SHA and are still present individually here. Rebase onto `main` before opening !7, once all agents have landed, or the MR replays sprint 03.
- The intent research's premise for this sprint was wrong — it assumed embeddings needed raw `httpx` because LangChain drops `usage.cost`. The SDK exposes embeddings directly with cost first-class. Re-verifying before building saved a parallel error path.

- WI3 correctly returned `partial` rather than reaching outside its scope: adding `embed` made `llm_app` multi-command, so Typer's single-command shortcut stopped applying and `test_llm_cli_wiring.py`'s `invoke(llm_app, ["hi"])` needed `["chat", "hi"]`. Fixed separately. No user-facing change — real invocations were always `app llm chat`.
- Rebased with `--onto origin/main 38455c3` to replay only sprint 04's eleven commits; a plain rebase hit repeated docs conflicts replaying sprint 03.

- AC1/AC2 hand-run live: 1536-wide vector, tokens and cost. Exposed a display defect — `_cost_text` rendered a real `1e-07` as `$0.000000`, indistinguishable from free, and sub-microdollar is the *common* case for embeddings. Fixed to `<$0.000001`; chat's format left byte-identical.

## Backlog proposals

## Verify
Round 1: approved — AC1–AC5 pass, D1 and D3 hold, no scope creep. Gates clean, 348 passed in 2.88s.
Reuse confirmed structurally: `errors.py` and `retry.py` are absent from the diff, and request counts show 3 attempts for a retryable class, 1 for a non-retryable one and for the width mismatch. AC5 is asserted on the serialised request body, not on call kwargs.
Verifier mutation-tested the cost fix (plain `.6f` turns exactly one test red) and disclosed briefly overwriting a working-tree file during a regression check; sprint lead re-verified the tree clean and the suite green afterwards.
Approval withheld — author and reviewer are the same account (note #67).
