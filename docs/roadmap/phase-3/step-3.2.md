---
phase: 3
step: "3.2"
title: Consultation UI spec
summary: The binding UI specification for the customer consultation experience — list, chat view, conversation state machine, sources, tool-result renderers, recommendation cards, i18n keys, and stub fixtures.
effort: 2
dependencies: ["2.2"]
---

# Step 3.2 — Consultation UI spec ✓ (done 2026-08-27)

**Effort: 2** — produced by the **ui-ux-designer** during phase planning and
reconciled with the architect's backend contract by the coordinating PM.

Deliverable: [`ui-spec.md`](ui-spec.md) — binding for every Phase-3 frontend
step (3.4, 3.6, 3.10, 3.15), exactly as the Phase-2 ui-spec was.

Reconciliations applied (see ui-spec §14 for the full list):

- Typing indicator derives **solely** from `chat.activeOperationId` — the
  chat UI never reads the admin-only `/api/operations`.
- Stale-turn recovery: `CHAT_TURN_STALE_SECONDS = 150` client constant
  mirroring the backend healing threshold (shared-knowledge §Chat response
  job & stale-turn healing).
- Message-part field names pinned in shared-knowledge (§Persisted JSONB
  shapes, §Tool result schemas); chat titles server-generated; message max
  length 4000; concurrent turns → 409 `response-pending`.

## Verification

- `docs/roadmap/phase-3/ui-spec.md` exists, is referenced as binding by
  steps 3.4/3.6/3.10/3.15, and contains no unresolved contract questions.
