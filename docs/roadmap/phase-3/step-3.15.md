---
phase: 3
step: "3.15"
title: Wire advisor UI live (S2)
summary: The full advisor experience in the browser — real tool results, sources, and recommendation cards rendered from persisted message parts, edge cases per spec, and resume-after-close re-verified against real agent turns.
effort: 3
dependencies: ["3.10", "3.13", "3.14"]
---

# Step 3.15 — Wire advisor UI live (S2)

**Effort: 3** — the components exist and the hooks are real; this step is
end-to-end verification against real agent output plus the edge-case
polish. **Starts only after 3.13 + 3.14 are merged.**

Binding contracts: `docs/roadmap/phase-3/ui-spec.md` and
`docs/roadmap/phase-3/shared-knowledge.md`. Agent: **frontend-dev**.

## Outline

- First action: regenerate API types (consistency check — the surface froze
  at 3.3; any diff is a stop-and-report).
- Render real message parts end-to-end; verify each renderer against a real
  agent turn's persisted JSON (not just fixtures): labelled tool blocks,
  subtle rows for `record_preference`/`flag_unknown_bike`, generic fallback
  for `present_recommendations`, de-duplicated sources with working
  external links, cards with real `/media` images (dev `VITE_API_URL`
  prefix proven in the browser).
- Edge handling per ui-spec: empty part arrays, a `failed` tool_call entry
  (generic fallback + error note), unknown tool name → generic renderer,
  imageless recommendation → fallback box.
- Resume-after-close re-verified with a real agent turn (long turns make
  the typing state meaningful); stale-turn fallback verified by killing the
  worker mid-turn (composer re-enables after `CHAT_TURN_STALE_SECONDS`, the
  next send heals server-side and completes).
- Any fixture/shape mismatch found here is a contract bug — stop and
  report, don't adapt the components silently.

## Verification

- In the browser: a full interview shows labelled tool results, a
  collapsible sources section with working external links, and
  recommendation cards with image + specs + rationale; close the browser
  mid-typing, reopen, the answer arrives; kill the worker mid-turn, wait
  out the stale window, re-send completes. `make frontend-test` + lint +
  typecheck green. **This closes milestone M4.**

## Risks / notes

- This is a verification-heavy step, not a building step — if it uncovers
  renderer bugs, fix them here; if it uncovers shape drift, the fix belongs
  on the backend side (report it).
