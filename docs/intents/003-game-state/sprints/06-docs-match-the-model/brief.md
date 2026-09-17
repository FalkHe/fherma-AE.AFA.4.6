---
author: sprint
owner: human
created: 2026-09-16
stage: approved
---
# Sprint 06: the general docs describe the model that exists

## Outcome
The general docs describe the model that exists: nothing in `docs/general/` names an entity the schema does not
have, position reads as the creature's, combat and turn order read as deferred, several characters per user is
stated, and the module index points at the new module doc.

## Acceptance criteria
- AC1: §7 items 1–13 are applied to `docs/general/model.md` — the entity diagram, the ownership section, the position paragraph, the combat paragraph, the lifecycle rows, the Purge row and known gap 1. Grepping `Playthrough` returns nothing; `Encounter` and `Initiative` appear only as explicitly deferred (← D2, D8, D10, D12, D13).
- AC2: §7 items 14–15 are applied to `docs/general/architecture.md`: `campaign_run_members` replaces `playthrough_members`, "one character per member" is gone (← D13), the state panel's turn order reads as deferred (← D8).
- AC3: §7 items 16–17 are applied to `docs/general/glossary.md`: **campaign run** and **adventure run** replace **Playthrough**, each in one line; **Encounter** and **Initiative** are marked deferred; a **seed player character** entry exists.
- AC4: §7 items 18–19 are applied to `docs/general/app-vision.md` and `docs/general/requirement-map.md`.
- AC5: `docs/modules/playthrough.md` exists — what the module owns, its five tables, its surface — and `docs/README.md` lists it.
- AC6: `roadmap/Stage-01/README.md`'s four open decisions (`:315`-`:318`) and two conditional rows (`:385`-`:386`) are marked closed, and **no other roadmap text is edited** — roadmap documents are history, and correcting a register is how it stops being trustworthy.
- AC7: `make lint` passes; no code, schema or migration changes in this sprint.

## Decisions
← D2, D3, D8, D10, D12, D13, D14

## Assumptions
- Every correction is enumerated in `decisions/model.md` §7 with file:line; this sprint applies that list and adds nothing to it. Anything found that is not on the list goes to `progress.md` under Backlog proposals rather than being fixed here.

## Out of scope
No code, no migration, no test change · the roadmap and the intent's own documents · player-facing wording, which is i18n and belongs to the UI phase (← D2).
