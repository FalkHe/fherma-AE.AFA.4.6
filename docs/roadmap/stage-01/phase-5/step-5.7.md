---
phase: 5
step: "5.7"
title: Extract fencing helpers to a shared module
summary: Pure refactor — move FENCE_START/FENCE_END, the lookalike stripper and the fence() helper from extraction.py into new app/llm/fencing.py; extraction re-imports; zero behaviour change.
effort: 1
dependencies: []
---

# Step 5.7 — Extract fencing helpers to a shared module

**Effort: 1** — a mechanical move with a green suite as the proof; kept
separate from 5.8 so the feature diff stays readable (refactor-first rule).

Binding contract: `docs/roadmap/stage-01/phase-5/shared-knowledge.md` (D4). Agent:
**backend-dev**. Zero deviations — a deviation is a stop-and-report.

## Outline

- New `backend/app/llm/fencing.py`: move verbatim from
  `backend/app/llm/extraction.py` — `FENCE_START`
  (`<<<UNTRUSTED-DOCUMENT-START>>>`), `FENCE_END`, `_FENCE_LOOKALIKE`
  (exported as a public name), `_FENCE_REPLACEMENT`, and `fence(text)`.
  Module docstring states the rule: this is the one definition site for
  untrusted-content fencing; any prompt surface interpolating retrieved or
  user-derived text imports from here.
- `backend/app/llm/extraction.py`: re-import; no other line changes; prompt
  templates untouched.
- Move/repoint the existing fence unit tests to a `tests/llm/test_fencing.py`
  (or keep in place with imports updated — whichever keeps the diff
  smallest).

## Verification

- Suite + lint green; `git grep "UNTRUSTED-DOCUMENT-START"` shows the
  constant defined once (fencing.py) and referenced elsewhere.
- Behaviour proof: the extraction tests that assert fenced prompts still
  pass unmodified (except import paths).

## Risks / notes

- Zero wire/behaviour change is the contract — if any test needs a
  *semantic* edit, stop and report.
- Append (`### Step 5.7`) to `shared-knowledge.md` only if the public names
  differ from D4's list (they shouldn't).
