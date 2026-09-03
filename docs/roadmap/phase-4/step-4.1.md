---
phase: 4
step: "4.1"
title: Consultation UI (superseded — moved into Phase 3)
summary: SUPERSEDED. The consultation UI was pulled into Phase 3's parallel frontend track (steps 3.2, 3.4, 3.6, 3.10, 3.15) so each feature is built by frontend and backend in parallel. Phase 4 keeps only catalogue browsing (4.2) plus the one-line recommendation-card link wiring.
effort: 0
dependencies: []
---

# Step 4.1 — Consultation UI (superseded)

**This step no longer exists as Phase-4 work.** During the Phase-3 slicing
(2026-08-27) its entire scope moved into Phase 3's frontend track so the
consultation feature is built by frontend and backend in parallel, mirroring
the Phase-2 two-track pattern:

| Former 4.1 scope | Now lives in |
|---|---|
| Backend message-part contract (`sources`, `toolCalls`, `recommendations`, `activeOperationId`) | Phase-3 steps 3.1 + 3.3 |
| Consultation list + chat view + composer + markdown bubbles | Phase-3 steps 3.2 (ui-spec) + 3.4 |
| SSE seen/typing state machine, live wiring | Phase-3 step 3.6 |
| Sources display, four tool-result renderers, recommendation cards | Phase-3 steps 3.10 + 3.15 |
| End-to-end QA script (register → interview → cards → resume) | Phase-3 steps 3.16 + 3.17 |

Binding contracts: `docs/roadmap/phase-3/shared-knowledge.md` and
`docs/roadmap/phase-3/ui-spec.md`.

**One piece of consultation work remains in Phase 4**, attached to step 4.2:
recommendation cards render unlinked in Phase 3 (the catalogue detail page
does not exist yet); step 4.2 adds `/catalogue/:productId` and the one-line
card link (the persisted recommendation snapshot already carries
`motorbikeId`).
