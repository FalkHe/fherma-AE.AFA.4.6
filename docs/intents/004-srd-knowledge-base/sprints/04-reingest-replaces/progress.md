---
author: sprint
owner: agent
created: 2026-09-16
updated: 2026-09-16
stage: draft
---
# Progress: Sprint 04 — a second import replaces the corpus

| WI | Status | Note |
|---|---|---|
| 1 | running | |
| 2 | open | |
| qa | running | |

Status: `open | running | done | failed`

## Issues
- Three of the five criteria were already true when this sprint started: the previous sprint's import already replaces the rulebook in one step and already leaves it untouched when a run fails. Nothing proved it, though, because every existing failure test started from an empty rulebook and none ran the import twice. Proving them is most of this sprint; only two criteria needed new code.
- Uniqueness of a passage's citation held by luck, not by rule. Two rules whose headings differ only by a disambiguating suffix collapse to the same trail, and nothing in the database prevented the collision; it was reproduced deliberately, though it does not occur in the real rules text today.
- A passage's position is now counted within its heading trail rather than within its markdown section. The approved module-structure attachment describes the older meaning; the trail is what a citation points at, so uniqueness has to hold against it. The attachment is the human's to amend.
- The research asked whether a failed import should put the previously stored rules file back. The criterion says the corpus and the repository must never disagree, which settles it: it restores.
- Fourth merge request in an unmerged chain. Each targets its predecessor.

## Backlog proposals
<none yet>

## Verify
<pending>
