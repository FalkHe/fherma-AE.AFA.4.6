---
author: sprint
owner: agent
created: 2026-09-16
updated: 2026-09-16
stage: draft
---
# Progress: Sprint 02 — fetch and chunk

| WI | Status | Note |
|---|---|---|
| 1 | done | the source downloads to a fixed path, replacing in place, and a failed download leaves the stored copy intact; 10 tests |
| 2 | running | |
| 3 | open | |
| 4 | done | the rules document and its licence ship in the repository; attribution in the project README |
| qa | done | one acceptance test per criterion, AC1-AC6 |

Status: `open | running | done | failed`

## Issues
- Branched off sprint 01 rather than the default branch: this sprint extends the rules module sprint 01 created, which the human has not merged yet, and building from the default branch would have meant duplicating it. The merge request targets sprint 01's branch and will retarget itself when that one merges.
- Two of the research's open questions were treated as already settled rather than escalated: storing the rules document in the repository is what the approved decision D3 asks for, and the specific public source was the recommendation the human approved at intent level. Its size, about 1.9 megabytes per revision, is the fact the human may not have pictured.
- The passage size cap and overlap are proposals, not measurements; the first place the choice becomes testable is the relevance floor in backlog line 06. Small sections stay separate passages rather than being merged, because merging would blur the citation.
- The criterion asking that no passage exceed the embedding window is hollow as written: the window is far larger than the largest section, so nothing would ever split. A deliberately smaller cap makes the split real and the citations usable.
- `plan.md` is over its word cap for the same reason sprint 01's was: verbatim interface identifiers the parallel work items must share.

- The project README was unreachable from inside the test container, which mounts only the backend directory, so the work item added a read-only mount of that one file to make the attribution criterion checkable. It is the sprint's only infrastructure change.

## Backlog proposals
<none yet>

## Verify
<pending>
