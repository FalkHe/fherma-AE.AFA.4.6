---
author: intake
owner: human
created: 2026-09-15
stage: approved
---
# Sprint 06: a prompt resolves by id at a named version

## Outcome
`app prompt show <capability>/<kind>/<id>` prints the text of a named prompt
version, and an unknown id fails differently from a malformed one.

## Acceptance criteria
- AC1: a prompt file placed under its owning module's `prompts/` directory resolves by id and its text is printed verbatim.
- AC2: `--version v1` prints that version; with no flag, the highest version resolves.
- AC3: the resolved version identifier is printed alongside the text, so a run can record which version it started with (D5).
- AC4: an id that matches nothing fails as not-found; an id that breaks the id format fails as invalid — different codes, both non-zero.
- AC5: all of it is asserted without an API key or a database — this is the filesystem.

## Decisions
← D5

## Assumptions
- Resolution mirrors `backend/app/modules/content/service.py` — a root constant, `v<n>` directories, an id regex, and the `NotFound` / `Invalid` split of `content/errors.py`.
- An id resolves against its **owning capability's** prompt directory; the root `modules/game/prompts/` named in the roadmap is the logged error, not the target.

## Out of scope
Storing the pinned version on a run (phase 5) · composing a system prompt from
fragments and showing the effective prompt (phase 10) · the free-text override
(phase 10) · authoring any actual DM prompt content.
