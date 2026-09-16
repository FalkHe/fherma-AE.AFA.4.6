---
author: sprint
owner: agent
created: 2026-09-16
updated: 2026-09-16
stage: done
---
# Progress: Sprint 02 — fetch and chunk

| WI | Status | Note |
|---|---|---|
| 1 | done | the source downloads to a fixed path, replacing in place, and a failed download leaves the stored copy intact; 10 tests |
| 2 | done | 2,132 citable passages from the real document, none over the cap; 6 tests |
| 3 | done | `srd ingest --dry-run` reports path, size, passage and token counts and sample headings |
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
- The rules text is a volunteer conversion of the publisher's original, carrying its own "work in progress, no guarantees" warning. Nothing this sprint puts it in front of a player, so no decision is needed today; the forcing point is the first sprint that lets rules text reach a player's screen. Carried onto backlog line 05 as a named precondition.
- A failed download now names an internal temporary file the operator will never find, rather than the source it tried to read. Cosmetic.
- The rules document is read and counted twice per rehearsal, once to check it is usable and once to report on it. Harmless at this size; worth reusing the first pass when the real import lands.

## Gates
Lint, both suites and the live-database run all pass (573 offline, 4 live, 53 frontend). The dry run was also executed for real against the public source: it fetched 1,878,072 bytes, reported 2,132 passages and 502,818 tokens, and left the working tree clean.

## Verify
Round 1: changes-requested. Two failures. A download that answers but returns something that is not readable rules text replaced the good stored copy and then crashed with a raw error dump, so the promise that a failed import leaves the stored rules intact held only for outright download failures. And the rules component's own description still said that importing rules was a later sprint's work.
Round 2: approved. Both failures fixed and re-checked by running the behaviour: a download that answers with something other than rules is now refused before it can replace the good copy, and the component's own description matches what it does. No regressions.
