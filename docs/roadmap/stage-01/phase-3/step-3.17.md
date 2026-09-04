---
phase: 3
step: "3.17"
title: Phase-3 acceptance run
summary: The phase done-criterion end-to-end with evidence — fresh browser interview with visible tool results, sources, typing states and cards, resumability including a killed worker, and the demo script — then tag phase-3-done.
effort: 3
dependencies: ["3.15", "3.16"]
---

# Step 3.17 — Phase-3 acceptance run

**Effort: 3** — an execution-and-evidence step across both tracks, plus the
moved-in consultation-UI criteria formerly in step 4.1.

Binding contracts: `docs/roadmap/stage-01/phase-3/shared-knowledge.md` and
`docs/roadmap/stage-01/phase-3/ui-spec.md`. Agent: **qa-frontend** leads (browser
walk with screenshots), **qa-backend** re-runs the demo script and verifies
DB effects independently of the dev reports.

## Outline

- Fresh registration → "Ask the advisor" → the advisor's greeting + opening
  question arrives via the typing state → browser interview: seen ✓,
  animated typing over SSE, markdown replies, ≥3 distinct labelled tool
  results visible, collapsible sources with working external links,
  recommendation cards (image, specs, rationale) — screenshots as evidence
  for each grading-relevant surface.
- Resumability: close the browser mid-typing → reopen → the reply arrived;
  kill the worker mid-turn → stale window elapses → UI recovers → re-send
  completes (server-side healing).
- Preference lifecycle: revise a stated budget → supersession visible in
  the DB; uncatalogued bike mention → exactly one backlog row in the admin
  UI; repeat mention adds none.
- Failure path: blank `OPENROUTER_API_KEY` in the worker → apologetic
  assistant message renders as a normal bubble, no hung typing state.
- Soft delete: delete a consultation from the list (confirm dialog) → gone
  from the list, deep link 404s, DB row retains `deleted_at`.
- `demo_conversation.py` green as an independent check; ownership probe (a
  second account gets 404s and sees nothing over SSE).
- Record findings; non-blocking polish goes to `open-questions.md` / Phase
  5; tag `phase-3-done`.

## Verification

- The roadmap Phase-3 done-criterion holds end-to-end with recorded
  evidence: a scripted conversation over the API yields a plausible
  interview, visible tool calls, recommendations grounded in approved
  models, and sources attached — plus the browser experience above.
