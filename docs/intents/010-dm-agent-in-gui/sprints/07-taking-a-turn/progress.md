---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
stage: done
---
# Progress: Sprint 07

| WI | Status | Note |
|---|---|---|
| 1 | done | composer: open form, three closed in-voice lines |
| 2 | done | thinking line: spinner plus wording in a live region |
| 3 | done | transcript renders the thinking line at its foot |
| 4 | done | notice stream via EventSource, reopens after a fatal close |
| 5 | done | transcript read exposes whether a turn is unfinished |
| 6 | done | send, optimistic row, composer state, tick re-read |
| 7 | done | round 2: stream polls with its own session; fallback re-read while a turn runs |

Status: `open | running | done | failed`

## Issues
Human asked for speed: minimal tests, visual polish not gated. No qa agent; component tests per work item.
Accepted the architect's assumptions: the composer stays closed with its own wording while a question or roll is pending (buttons arrive in sprint 09); a turn that breaks mid-flight keeps the thinking line until sprint 10's give-up timer.

## Backlog proposals
The notice stream had been broken on the server since it was built (sprint 03 never had a browser consumer to notice); a browser acceptance run against the live stack would have caught it before a verifier did.

## Verify
Round 1: changes-requested — AC2, AC4, AC5. The notice stream endpoint fails server-side on its first poll (the request-scoped database session is used inside the generator after the handler returned), so no tick ever reaches the screen and the browser never sees a close it could reconnect from.
Round 2: approve, no failed criteria.
