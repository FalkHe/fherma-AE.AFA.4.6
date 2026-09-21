---
author: sprint
owner: agent
created: 2026-09-21
updated: 2026-09-21
stage: done
---
# Progress: Sprint 07a

| WI | Status | Note |
|---|---|---|
| 1 | done | `dice.py`, the `_rng` seam, `derive_formula` for six kinds |
| 2 | done | the five producers, sharing `use_exit`'s gate order |
| 3 | done | authored difficulty floor raised to 5, guide and tests |
| 4 | done | `app playthrough roll`, printing the derivation |
| 5 | done | module doc §13 and README |
| qa | done | 4 acceptance tests |

Status: `open | running | done | failed`

## Issues

- **Sprint 07 was split into 07a and 07b** — the largest in the intent. Research could not fit under its own cap
  even compressed. 07a derives and records a roll; 07b spends it once and adds `awaiting`. 07b is issue #35, new;
  rows 08 and 09 now depend on 07b.
- **This plan still runs ~25% over the word cap after the split.** The overflow is contract — five producer
  signatures and their payloads — not scope: splitting further would separate the dice from their only callers.
  Recorded rather than split again.
- **Two rulings from the product owner**, asked because research marked them product-visible:
  1. The SRD's difficulty table binds authored content as well as the DM, so the authoring floor rises from 1 to
     5 (AC5). Their principle was "SRD rules win". The 5–30 range came from D6 and matches the SRD's own table;
     the old floor of 1 came from the content schema and matches nothing. Greenhollow's authored checks are 8, 10,
     12, 12, 13, 14, so nothing shipped breaks. **This reaches outside the sprint's module** — flagged in the
     review.
  2. A monster's attack is chosen by the DM **by name** and derived from its stat block, never by position.
- Called, agent-level: `passive_check` records a `tool_call` at `dm` rather than a `roll`, since a `roll` needs
  faces and would be consumable · `_acted_this_turn` belongs to sprint 08 · a dice expression is capped at 20 dice
  of at most 100 faces.

- One `# noqa: B008` was added, on the `roll` command's `kind` argument alone. Ruff flags that one call and no
  other of the same shape, because `RollKind` is a `Literal` alias rather than a builtin and its exemption check
  does not resolve aliases. Documented in place, narrowest possible scope.

## Backlog proposals

<none yet>

## Verify

Round 1: changes-requested — AC1, AC2, AC4a and AC5 all OK, and the verifier proved the load-bearing ones by
mutation: picking a monster's attack by position instead of by name fails, and truncating the ability modifier
instead of flooring it fails. The gap is `test_resolve_roll_request_reuses_the_requests_own_stored_values`:
replacing the stored-formula re-use with a fresh derivation leaves all 872 unit and 67 database tests green,
because nothing changes between request and answer in its scenario. To bite it must make a fresh derivation
produce a *different* formula — change the actor's ability score after the request — and assert the answer
follows the stored one.

Also noted: `README.md:263` cites `playthrough/cli.py` for the command, which lives in `commands.py`; the same
wrong filename is already on `main` at line 250.

Round 2: approve — `git diff` over `backend/app/` is empty since round 1, so every earlier confirmation stands by
construction. The verifier re-applied its own mutation: a fresh derivation in place of the stored formula now
fails the guard with `assert 5 == 1`, the only failure in the suite. It notes the `formula` assertion alone still
would not bite — the modifier and total assertions carry the proof, which is the right place, since those are
what the player receives. Gates: lint, 872 engine-free, 53 frontend, 67 database.

Carried into 07b rather than fixed here: the module README cites `playthrough/cli.py` for the command, which
lives in `commands.py` — a slip already on `main`, in a section 07b will touch. `review.md` also runs over the
250-word cap.
