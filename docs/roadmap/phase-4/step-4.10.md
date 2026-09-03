---
phase: 4
step: "4.10"
title: Demo-script catalogue chapter
summary: Extend the Phase-3 demo assets with a replayable catalogue chapter — browse, filter, deep link, recommendation-card click-through, out-of-chat sources — so Phase-5's docs/demo work inherits a complete walkthrough.
effort: 1
dependencies: ["4.9"]
---

# Step 4.10 — Demo-script catalogue chapter

**Effort: 1** — documentation only; every command/URL already works after
4.9.

Binding contract: `docs/roadmap/phase-4/shared-knowledge.md`. Agent:
**docs-writer**. Zero deviations — a deviation is a stop-and-report.

## Outline

- Extend the Phase-3 demo walkthrough (wherever 3.16 landed it — the
  `demo_conversation.py` docstring/readme notes or its companion doc) with
  a catalogue chapter: sign in as a plain user → open Catalogue → apply a
  filter combination that visibly narrows (e.g. category + A2-only) →
  copy/reload the URL → open a model detail → point out verified specs,
  the article prose, the **Sources block** (the out-of-chat provenance
  surface) and image attribution → from a consultation, click a
  recommendation card through to the same detail page.
- Include the curl lines proving role scoping (plain user: 200 on
  `/api/catalogue-models`, 403 on `/api/products`, 404 on an unapproved
  id) so graders can replay the security story without the UI.
- Note the price-band caveat if still open (see `open-questions.md` OQ2):
  which step of the demo needs a verified price to shine.

## Verification

- A fresh reader can replay the chapter verbatim against the running stack
  with zero corrections (every URL, credential step and expected outcome
  spelled out).

## Risks / notes

- Documentation only — no code changes; if a documented behaviour turns
  out broken, report it instead of documenting around it.
