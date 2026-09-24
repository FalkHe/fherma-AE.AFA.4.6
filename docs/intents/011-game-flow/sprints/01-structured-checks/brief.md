---
author: fhit:architect
owner: human
created: 2026-09-24
updated: 2026-09-24
stage: approved
---
# Sprint 01: Checks name their ability and skill as data

## Task
Give every authored hidden discovery and every authored fixture action an explicit ability and optional skill beside its difficulty, fill them in for the Greenhollow adventure, and make the rules engine derive active checks, passive checks and saving throws from those fields instead of reading them out of prose. Keep one internal dice primitive; correct any formula derivation that is wrong today.

## Outcome
Every authored check in Greenhollow names its ability and skill as data, and content validation rejects one that does not.

## Acceptance criteria
- AC1: Given a hidden fact, when content is validated, then it carries an ability, an optional skill and its difficulty, and one without an ability is refused.
- AC2: Given a fixture action, then the same fields are present and validated.
- AC3: Given an active check, passive check or saving throw for an authored entry, when it runs, then the ability used is the authored one and no wording is parsed.
- AC4: Given the current game, when a turn is played, then nothing about play changes yet.

## Decisions
← intent §1.1, §1.2

## Assumptions
- The existing prose describing how a fact is discovered stays as guidance for narration; the new fields are required, and the content is edited in the same change.
- The entry points for checks and saves keep their current names, so the running game keeps working.

## Out of scope
The situation read, any graph code, new campaign content.
s