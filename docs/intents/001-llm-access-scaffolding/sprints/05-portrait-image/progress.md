---
author: sprint
owner: agent
created: 2026-09-15
updated: 2026-09-15
stage: draft
---
# Progress: Sprint 05

| WI | Status | Note |
|---|---|---|
| 1 | open | |
| 2 | open | |
| qa | open | |

Status: `open | running | done | failed`

## Issues
- Research made one live image call to establish the response shape (~$0.067). Third sprint running where the intent research's transport assumption was wrong and re-verifying avoided building a parallel error path.
- `usage.cost` absent reads back as `Unset()`, not `None` — it would crash `_cost_text` at `round(Unset(), 6)`.

## Backlog proposals
- **Portrait economics, for phase 7:** ~$0.067 and ~1.7 MB per portrait at the model's defaults. A character-creation flow that regenerates freely is materially expensive, and 1.7 MB per stored portrait adds up. `resolution` / `output_format` exist on `images.generate` if either needs tuning; choosing them is out of scope here.

## Verify
