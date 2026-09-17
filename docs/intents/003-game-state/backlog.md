---
author: intake
owner: human
created: 2026-09-16
updated: 2026-09-16
stage: approved
---
# Backlog

Sprint outcomes, dependency-ordered. Status: `open | running | done`.

**This phase has no player-facing surface and no sprint invents one.** Phase 5 owns every service and route, so
"verifiable by using the product" is **developer-visible** here: `make backend-test-db` goes green on statements about
what the schema accepts and refuses, against a real migrated database (← D9 as amended by D15). A weaker claim than a
screen somebody can use, and the honest one — this phase ships constraints, verified by watching them reject.

| # | Outcome (one verifiable statement) | Depends on | Issue | Status |
|---|---|---|---|---|
| 01 | The scratch-database fixture SRD shipped becomes a shared one: `tests/srd` keeps passing unchanged over it, and a second module reaches a real, migrated database through the same helper | – | #20 | done |
| 02 | A campaign run and its owner survive a migration round trip: on a fresh database `upgrade head` accepts a campaign run with an owner row, an untitled run and a third run of the same campaign for the same user, while refusing the same user twice in one run and an unknown status — and `downgrade base` leaves the baseline exactly as it was | 01 | #15 | done |
| 03 | Adventure progress cannot contradict itself: a campaign run records one row per adventure entered, refuses the same adventure twice, refuses a second *active* adventure beside the first, and refuses a row marked completed with no completion time | 02 | #16 | done |
| 04 | The world's objects hold what the authored content declares and nothing it does not: a creature carries hit points and armour class, an item attempting either is refused, hit points above the maximum are refused, a carried item cannot also stand in a scene, a character's position names the adventure run that scopes its scene, and one member may hold two characters | 02, 03 | #17 | running |
| 05 | The transcript is append-only, ordered and filterable: events written to a campaign run read back in write order by id alone, a DM-visibility event is absent from the player read while still present in the table, an unknown type or visibility is refused, and per-turn and per-run cost are exact sums over the rows | 02 | #18 | open |
| 06 | The general docs describe the model that exists: nothing in `docs/general/` names an entity the schema does not have, position reads as the creature's, combat and turn order read as deferred, several characters per user is stated, and the module index points at the new module doc | 02, 03, 04, 05 | #19 | open |

## Notes

- **01 adds no migration revision at all** — it is infrastructure. The schema then lands one
  additive revision per sprint in FK order, beginning at `0003` (SRD's `0002_srd_rules`
  landed meanwhile): 02 → `0003`, 03 → `0004`, 04 → `0005`, 05 → `0006` if it merges last.
  No sprint edits an earlier revision; 05 depends only on 02 and may run **in parallel with
  03 and 04**.
- 02 creates `backend/app/modules/playthrough/` with its `README.md` and the one `env.py`
  import (← D14); 06 writes `docs/modules/playthrough.md` + the index row.
- 06 carries §7 of `decisions/model.md`: 19 contradictions across six `docs/general/` files
  plus the index — its own sprint, one coherent hour of prose, landing last. **Roadmap
  documents stay untouched:** history, and correcting a register stops it being trustworthy.
- **01 promotes SRD's scratch-database fixture** (← D15); 02–05's criteria are
  `@pytest.mark.database` tests over it, `make backend-test` staying `--no-deps`. Phase 1's
  content module is loadable, so 04 is checked against `greenhollow/v1`.
- **Rejected as outcomes:** "a campaign run starts and instantiates its objects" — phase
  5's lifecycle service, which a schema sprint must not smuggle in; "the migration runs"
  alone — not a statement about the product; one sprint per table — `campaign_runs` and
  its member row prove nothing apart.
- Coverage: D1, D3, D6, D7, D11 → 02 · D2, D14 → 02, 06 · D4, D5 → 05 · D8 → 06 (the
  deferral) · D9, D15 → 01, then all · D10 → 03 · D12, D13 → 04.

## Proposals

<none yet>
