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
| 1 | done | positions now counted per heading trail, with the database enforcing uniqueness; real corpus still 2,132 passages and migrates cleanly |
| 2 | done | a failed import puts the previous rules file back byte-for-byte, and a broken restore cannot hide the real failure |
| qa | done | one acceptance test per criterion; four already passed against the previous sprint's work, one drove the restore |

Status: `open | running | done | failed`

## Issues
- Three of the five criteria were already true when this sprint started: the previous sprint's import already replaces the rulebook in one step and already leaves it untouched when a run fails. Nothing proved it, though, because every existing failure test started from an empty rulebook and none ran the import twice. Proving them is most of this sprint; only two criteria needed new code.
- Uniqueness of a passage's citation held by luck, not by rule. Two rules whose headings differ only by a disambiguating suffix collapse to the same trail, and nothing in the database prevented the collision; it was reproduced deliberately, though it does not occur in the real rules text today.
- A passage's position is now counted within its heading trail rather than within its markdown section. The approved module-structure attachment describes the older meaning; the trail is what a citation points at, so uniqueness has to hold against it. The attachment is the human's to amend.
- The research asked whether a failed import should put the previously stored rules file back. The criterion says the corpus and the repository must never disagree, which settles it: it restores.
- Fourth merge request in an unmerged chain. Each targets its predecessor.

## Backlog proposals
<none yet>

## Gates
Lint, both suites and the live-database run all pass (611 offline, 18 live, 53 frontend). A second live import was also run: same 2,132 passages at the same byte count for $0.010056, and the corpus afterwards reported 2,132 rules with a later import time, nothing duplicated and the stored file unchanged.

## Verify
<pending>
