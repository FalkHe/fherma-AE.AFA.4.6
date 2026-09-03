# Phase 3 — Open Questions

Unresolved issues blocking or endangering pinned Phase-3 contracts. Each
entry carries the surrounding knowledge an agent needs to resolve it.
**Resolved questions are removed from this file** and their outcome is
pinned in [`shared-knowledge.md`](shared-knowledge.md).

---

**Q4 (concurrent-turn race, found by M2 QA, 2026-08-27).** Two *truly
concurrent* `POST /api/chat-messages` requests for the same chat can both
receive 201 (each creating its own operation): `heal_stale_turn`'s
check-then-act sequence is not race-safe under simultaneous requests. Not
reachable through the UI (the composer disables via SSE far faster than a
human can double-send) and both replies do persist, so severity is low —
but the 409 contract is violated under a deliberate race. Candidate fixes:
`SELECT … FOR UPDATE` on the chat row in the message-POST path, or a
partial unique index on operations (`entity_id WHERE status IN
('queued','running') AND type='chat.response'`) — the latter needs a
migration and 3.1 is pinned as the only Phase-3 migration, so the lock is
the in-phase option. **Owner decision (2026-08-28): defer to Phase 4 —
fixed as step 4.5 (the migration-free row lock, least-effort option; see
Phase-4 `shared-knowledge.md` D7). Remove this entry when 4.5 lands.**

**N1 (demo-data note, from 3.12, 2026-08-27).** No approved model in the
dev DB carries a verified `msrp_eur` or `price_band`, so live
`cost_estimator` output has no purchase-price line (the honest-omission
path; unit-tested only). Before the M4/M5 demos, verifying a price band on
at least one approved model (owner action or the Phase-2 curation flow)
would make the demo materially stronger. Not a code defect.
**Resolved 2026-08-28 (owner decision, via Phase-4 OQ2): guessed demo
prices seeded on all 3 approved models (draft + verified rows); real
price research deferred past Phase 4 — the values are plausible but
unverified.**

**N2 (non-blocking polish, from the 3.17 acceptance walk, 2026-08-28).**
For **admin-role** accounts at a 390 px viewport, the AppBar's four toolbar
items (title + Consultations/Admin nav + theme toggle + account button)
overflow horizontally (`scrollWidth` 435 vs 390). Plain customer accounts
are clean; the Phase-3 chat surfaces themselves are responsive. Pre-existing
admin-nav layout, not a Phase-3 regression — route to Phase 5 polish.

**N2 — RESOLVED (2026-08-29, Phase-5 step 5.17 acceptance).** Re-verified in
a real browser at both 360 px and 390 px on the admin backlog and admin review
shells: `document.documentElement.scrollWidth === window.innerWidth` at both
widths, and the header element's width matches the viewport exactly — the
4.11 fixes (commit `c7340a3`) hold. The catalogue article table wrapper was
confirmed clean at 360 px in the same pass.

The same pass found a **distinct, pre-existing** overflow with a different
root cause, filed and fixed rather than folded into N2: wide GFM tables in the
admin review Documents tab (`ModelDocumentsPanel`) scrolled the whole page at
360/390 px, because only `CatalogueModelRoute` carried a table scroll wrapper.
Fixed in commit `4b0a1e5` by giving the panel its own module-local wrapper
(chat and catalogue rendering unchanged).

---

*(previously: no open questions, 2026-08-27)*

All items raised during the Phase-3 slicing were resolved by the owner the
same day and pinned:

- **D1 (phase rescope)** — accepted: the consultation UI (former step 4.1)
  lives in Phase 3's frontend track; Phase 4 keeps catalogue browsing —
  pinned in shared-knowledge's scope note and `roadmap.md`.
- **Q1 (models)** — the advisor gets its own `ADVISOR_MODEL` config key
  (added in 3.5; responder + agent loop); `CHAT_MODEL` stays the
  ingestion/extraction + utility model (query translation included). Exact
  model ids are `.env` values and may change — never hardcoded, never
  asserted in tests — pinned in shared-knowledge *Config keys* and *Chat
  response job*.
- **Q2 (who speaks first)** — the advisor greets and asks an opening
  question, like a seller in a real store; but a chat is only ever created
  by the explicit "Ask the advisor" button, never on page load. Pinned in
  shared-knowledge (*JSON:API resources* → `POST /api/chats`, *Chat
  response job*) and ui-spec §4/§5/§14.
- **Q3 (deletion)** — soft delete: `deleted_at` on `chats` (3.1),
  `DELETE /api/chats/{id}` (3.3), list affordance + confirm dialog
  (3.4/3.6). No restore UI. Pinned in shared-knowledge *DB schema* +
  *JSON:API resources* and ui-spec §4.
- **A1 (working tree)** — resolved: tree clean except the Phase-3 planning
  docs (committed at slicing end).
- **A2 (approved models for M3)** — resolved: DB prepared with approved,
  embedded models.
