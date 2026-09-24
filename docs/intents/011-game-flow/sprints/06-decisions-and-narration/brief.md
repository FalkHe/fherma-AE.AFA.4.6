---
author: fhit:architect
owner: human
created: 2026-09-24
updated: 2026-09-24
stage: approved
---
# Sprint 06: Narrow decisions and evidence-bound narration

## Task
Implement the focused decision strategies — reading a player's move, interpreting rules or recalled evidence, judging an ambiguous reference, assessing authored checks, exits, fixtures and consequences, choosing a monster action and choosing a world reaction — each with its own instructions, output shape, allowed evidence and validation, with rules lookup and history recall available as read-only aids to the strategies that need them, capped at three uses per decision. Narration is a separate call with no aids that turns public evidence into a draft nobody has saved yet.

## Outcome
An unsupported action or an invented reference proposed by the model is rejected, and narration runs with no tools and no private mechanics in its input.

## Acceptance criteria
- AC1: Given model output naming an unsupported action or an object outside the scene, then it is rejected and retried within a small fixed budget.
- AC2: Given a decision that may consult rules or older history, then at most three lookups happen before it answers.
- AC3: Given narration, then its input contains no hidden fact, difficulty or private intent and no tools are attached.
- AC4: Given a narration draft, then it stays available until it is recorded.

## Decisions
← intent §5; v2 "Read-only tools inside decide"; AC "narration uses recorded public outcomes and cannot call tools"

## Assumptions
- Structured output goes through the existing model access; prompts are new versioned files beside the current one.
- Item use has no operation; the game refuses it through decision and narration.

## Out of scope
The old system prompt (removed in sprint 09), scheduling.
