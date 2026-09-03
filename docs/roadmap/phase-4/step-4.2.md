---
phase: 4
step: "4.2"
title: Catalogue browsing (split — replaced by steps 4.3–4.11)
summary: SPLIT. The former effort-8 catalogue-browsing step was re-sliced (2026-08-28) into parallel backend/frontend steps 4.3–4.11 with max effort 4 each. See shared-knowledge.md for the binding contract and the mapping below.
effort: 0
dependencies: []
---

# Step 4.2 — Catalogue browsing (split)

**This step no longer exists as dispatchable work.** During the Phase-4
slicing (2026-08-28) its effort-8 scope was split into parallel-track steps
of max effort 4, with the open design points resolved and pinned in
[`shared-knowledge.md`](shared-knowledge.md) (decisions D1–D7).

| Former 4.2 scope | Now lives in |
|---|---|
| Backend visibility & filters ("ensure `/api/products` serves non-admins…") | **Superseded by D1**: a new read-only `catalogue-models` resource; `/api/products` stays admin-only. Services in 4.3, endpoints in 4.4 |
| Manufacturer filter semantics (the Phase-2b reserved decision) | **D2**: filter by manufacturer ULID; `GET /api/manufacturers` relaxed to `current_user` (4.4) |
| Catalogue list page + URL-persisted filters | 4.7 (on stubs; ui-spec by 4.6) |
| Model detail page + detail content | 4.8 (on stubs) |
| Recommendation-card link (`/catalogue/:motorbikeId`, ui-spec §9) | 4.9 (wire live, S1) |
| UX pass (ui-ux-designer) | 4.6 — done at slicing time (`ui-spec.md`) |
| QA (filters, deep link, unapproved unreachable) | 4.11 (plus demo-script chapter in 4.10) |
| ULID-vs-slug decision | **D5**: ULID, param name `:motorbikeId` (this file's former `:productId` spelling is superseded) |

Additionally pulled into Phase 4: **4.5** — the Phase-3 open-question Q4
concurrent-turn 409 race fix (migration-free row lock), pending owner
confirmation in [`open-questions.md`](open-questions.md).
