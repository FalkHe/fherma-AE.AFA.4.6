---
author: fhit:architect
owner: agent
created: 2026-09-17
updated: 2026-09-17
---
# Research: intent 005 — Game State Services

## Facts

State model read from intent 003 (approved), **not** from code — phase 3 is still building it. **Where the code
goes.** One module, `backend/app/modules/playthrough/` — five tables *and* the transitions over them (← D14,
`003-game-state/decisions/model.md` §2.1/§2.3). One-way edges: `game` → `playthrough.service`; `playthrough` →
`content.service`. Services are modules of functions owning the transaction boundary; routes never commit
(`AGENTS.md`, `docs/architecture.md:39`; `users/service.py:18`-`28`, `srd/errors.py:1`-`10`, `users/routes.py:10`).

**Existing seams.** `CurrentAuth`/`CsrfAuth` (`auth/dependencies.py:21`,`:40`); envelope + `ErrorCode`
(`core/errors.py:17`-`34`,`:43`); `CamelModel` (`core/schemas.py:7`); `ID_TYPE` (`core/ids.py:12`); `DbSession`
(`core/db.py:52`). Content: `content/service.py:73` `load_campaign`, `:319` `load_scene`, `:330`
`load_object_template`; `Scene.exits` may be empty (`content/schemas.py:104`), `Attack.damage` is a verbatim dice
expression (`docs/modules/content.md:115`); `srd/service.py:44` `require_corpus` guards "no rules ingested". Per-call
cost exists: `Usage(prompt_tokens, completion_tokens, cost_usd)` (`core/llm/service.py:70`-`73`, `:211`). Determinism
precedent: the `_random()` seam monkeypatched in tests (`core/llm/retry.py:45`-`47`,
`tests/core/llm/test_retry.py:324`). Real-DB fixture to reuse: `tests/srd/conftest.py:85` (← D15,
`@pytest.mark.database`, `make backend-test-db`).

**Dice candidates** (`docs-lookup`; no dice code or dependency today, `backend/pyproject.toml`). `dice` **4.0.0** —
MIT, 2023-05-18, needs `pyparsing`; `dice.roll(expr, random=<Random>)` injects the RNG per call
(`dice/elements.py:114`,`:223`; local wheel + PyPI). `d20` **1.1.2** — 2021-07-08, pins the abandoned
`lark-parser~=0.9.0`, RNG is module-global `random` with no seam (`d20/expression.py:405`-`407`), richer D&D semantics
(context7 `/avrae/d20`), 3.12 unverified. Stdlib `random.Random` covers all the game asks: `NdM±K`, `d20 + bonus` vs a
DC (`docs/general/glossary.md:8`-`16`); a passive check is `10 + bonus`, **no roll**.

## The transition list (what actually changes a row)

Superseded in detail by [decisions/mechanics.md](decisions/mechanics.md) after the architecture discussion of
2026-09-17; the shape that survives is: **the surface is the list of game mechanics, not a generic write path.**

| # | Transition | Writes | Notes |
|---|---|---|---|
| T1 | `start_campaign_run` | `campaign_runs` (`setup`) + owner member + eager `objects` for every adventure | pins `content_version` (← 003-D7); **does not** enter an adventure (← D3) |
| T2 | `create_character` | one creature row, `member_id` set, `template_id NULL`; run → `ready`; first narration → `active` | the only generic object write (← D4) |
| T3/T4 | `rename_run`; `archive_run` / `unarchive_run` | `title`; `status` active↔archived | ← 003-D3, D11 |
| T5 | `enter_adventure` | `adventure_runs` insert + placement + `adventure_started` | explicit call; at most one active (partial unique index) |
| T6 | `use_exit` | position, or `adventure_runs.status` + `completed_at`, or `campaign_runs.status` → finished | one mechanic for scene change and adventure end (← D8) |
| T7 | `attack` / `damage` / `interact` / `take` / `drop` / `give` / `use_item` | `objects` stats, `owner_object_id`, position | mechanics over ids + roll ids (← D2, D5) |
| T8 | `request_player_roll` / `resolve_roll_request` / `roll` / `passive_check` / `resolve_check` / `resolve_save` / `ask_player` | `events` only | dice + formula derivation (← D6) inside the transition that records the roll |
| T9 | `append_event` | `events` insert | visibility, cost, `turn_id`, `actor_member_id` (← 003-D4); called by every row above |

**Reads, not transitions:** list my runs (archived included); events after an id at visibility `player`; the SSE
`updated` signal; who is in this scene; run cost; the member's character — which must raise when it finds more than one
(003 §3.6). **Arithmetic inside the above, never its own service:** ability modifiers, hp clamping, `d20+bonus` vs
DC/AC, passive `10+bonus`, `bypassed_by`, the one-action-per-turn count, roll consumption.

**Combat without a model (← D7):** checked against 003's tables — `attack` needs `armour_class`, `damage` needs
`current_hp` / `is_alive`, the per-turn action count needs `events.turn_id`, initiative needs only a `roll` event. All
exist. No encounter row, no pointer, no `in_combat` flag; 003-D8 stands.

## Options

**A. Service layout** (all keep "module of functions"). **A1** one flat `service.py` — what every module here does,
but ~10 transitions plus dice in one file, which §2.1 predicts outgrowing. **A2** a `service/` package re-exported
from `__init__` — §2.1's mitigation, but re-export binds names at import time, which `AGENTS.md` says breaks
monkeypatching. **A3** the same package with submodules imported directly — no patch hazard, same module edge.

**B. Per-owner access** — every transition takes the acting `user_id`. **B1** an internal `_require_member(db, run_id,
user_id)` first in every transition: the one gate `game`'s tools also pass, since they never touch a route; held by
review and test, not by types. **B2** a FastAPI dependency resolving membership: ergonomic, but agent tool calls
bypass routes, so it is no gate. **B3** B1 authoritative plus B2 for route ergonomics. Either way an unknown or
foreign run answers `NOT_FOUND`, never a distinct "forbidden".

**C. Rejection** — `ApiError` straight from the service (`users/service.py:22`) vs. a `PlaythroughError` hierarchy
(`srd/errors.py` shape) mapped at the route; the agent's tools are non-HTTP callers, which argues for the hierarchy.

**D. Dice.** **D1** stdlib `random` + a small parser in `playthrough/dice.py` behind an `_rng()` seam: no dependency,
covers every expression the game uses, mirrors `core/llm/retry.py:45`; we own the grammar and its error messages,
needed anyway — "invalid dice expressions" is graded (`docs/general/requirement-map.md:15`). **D2** `dice` 4.0.0:
maintained, per-call RNG injection is clean determinism, but a new dep plus `pyparsing` and far more notation than the
game uses. **D3** `d20` 1.1.2: D&D-native, but 2021, an abandoned `lark-parser` pin, no RNG seam, 3.12 unverified — it
fails the "stack has no answer" test.

**E. Cost** — `SUM(cost_usd)` over `events`, no denormalised total (← D4, §4.5); per turn `GROUP BY turn_id` on
`ix_events_campaign_run_id_turn_id`. A read function in `playthrough.service` behind the same B1 check, never in a
player-facing payload (`docs/general/architecture.md:77` puts it in the developer drawer). **Not built here:** no
encounter, initiative or turn order (← D8, phase 8); the four override columns stay NULL (← D6).

## Recommendation

A1 now (split to A3 when it hurts), B3 with B1 authoritative, C as a `playthrough` error hierarchy, D1 stdlib dice
behind an `_rng()` seam, E as a membership-gated `SUM` read.

## Open questions

All answered on 2026-09-17 and recorded in `decisions.md`: campaign run finishes automatically on the last adventure's
ending exit, adventures are entered explicitly (D3); archived runs are read-only and listed (D12); a visible roll shows
kind, faces, modifier, total, pass/fail on the consuming `tool_call`, a refused mechanic is a `dm`-visibility event
(D11); cost is owner-only in the developer drawer (D14); phase 5 ships the lifecycle routes, the events read and the
SSE signal, while the turn and roll-click routes belong to phase 8 (D10, D14); domain codes go to the shared
`core/errors.py` enum as the other modules do; rolls are reproducible from stored faces, `_rng()` is test-only (D13).

## Alignment check after intent 003 landed (2026-09-17, `e78fe97`)

003 landed exactly as approved — no decision was added, `content/schemas.py` is untouched, and none of the changes this
intent asked for upstream were folded in. So they are **no longer brief edits: they are this phase's own additive
migration `0007`, plus one content-schema change.** Each line below is an item for the refine run.

**A. Schema changes → one migration `0007` in this phase's first sprint** (`backend/alembic/versions/`,
`down_revision = "0006"`; the CHECK names are bare — `status`, `type` — so `op.drop_constraint("status",
"campaign_runs")` + recreate):

- A1 `campaign_runs.status` CHECK → `('setup','ready','active','archived','finished')` (← D3). `server_default`
  stays `active`? **No** — the lifecycle creates in `setup`, so the default becomes `setup`; the acceptance test in
  003 sprint 02 that inserts without a status and expects `active` must be adjusted. Update `models.py`,
  `playthrough/README.md` and `docs/modules/playthrough.md` §3 in the same sprint.
- A2 `objects.template_id` → nullable (← D4). Alternative to weigh in refine: keep `NOT NULL` and write the sentinel
  `seed-player-character` for the seed-instantiated PC — no migration, but a content id that names no template, which
  003 ruled out for every other content column. Recommendation: nullable.
- A3 `events.type` CHECK → the twelve values of D9. 003 sprint 05's acceptance test "unknown type refused" keeps
  passing; add the twelve to the model's docstring and `docs/modules/playthrough.md` §7.
- A4 Fix carried over from 003 sprint 05's backlog proposals: `CampaignRun.temperature` is `Mapped[float]` over
  `Numeric(3,2)` — make it `Mapped[Decimal]` before anything writes it. No migration.

**B. Content-schema changes** (`content` module, phase-1 code; a new `greenhollow/v2` or an in-place `v1` edit is a
refine decision — 003-D7 pins runs to a version, and no run exists yet, so editing `v1` is safe today):

- B1 `Exit.kind: Literal["scene","adventure_end"] = "scene"`, `to` required only for `scene` (← D8); `lair-hollow`
  gains one `adventure_end` exit. The loader's exit validation (`content/service.py`) must accept `to = None` for
  `adventure_end`.
- B2 `SeedCharacter.inventory: list[ContentId]` referencing item templates; greenhollow's seed inventory becomes
  `["shepherds-knife", …]` and the missing items become templates. The PC's `instance_key` for carried seed items
  follows 003 ASSUMPTION 9 (`pc:<member_id>:1/shepherds-knife:1`).

**C. Facts from the landed code the mechanics must respect** (no change, but the sprint plans must know):

- C1 `objects.state` and `events.payload` are JSONB with **no per-kind validation in the database**; the per-kind
  Pydantic models 003 §6 deferred are this phase's `playthrough/schemas.py`. Reassign `state` whole, never mutate.
- C2 `events.id` ordering is monotonic **within one process** only (003 sprint 05 proposal). Every write path here is
  one request-scoped transaction and the stack runs one uvicorn process; state the assumption in the module doc rather
  than adding a sequence column.
- C3 `events.turn_id` has no referent and no table; D5/D7's "consumed in the same turn" and "one action per turn" are
  scans over `WHERE campaign_run_id = ? AND turn_id = ?` on `ix_events_campaign_run_id_turn_id` — the index exists.
- C4 `adventure_runs` rejects deleting a row a positioned object points at; irrelevant to this phase (nothing deletes),
  but `use_exit` to an `adventure_end` exit must **not** clear positions — the characters keep standing in the last
  scene until `enter_adventure` re-places them (003 §3.1's one-statement placement).
- C5 The one-active-adventure rule is a partial unique index; `enter_adventure` catches `IntegrityError` and maps it to
  a domain code rather than pre-checking (one round trip, no race).
- C6 `docs/general/model.md:311`-`312` still describe "Start a campaign run" as instantiating all objects **and
  generating the player's creature** in one step. D3/D4 split that into `start_campaign_run` (objects, status `setup`)
  and `create_character` (status `ready`); the docs sprint of this phase corrects the two rows and adds `setup` /
  `ready` / `active` to §3 of `docs/modules/playthrough.md`.

**D. Confirmed fits, nothing to do:** position pair on the creature, `owner_object_id` inventory, promoted stats and
`hp_range`, per-event cost, membership root, `ck` names as documented, real-database fixture at
`backend/tests/database.py` (`scratch_db`) for this phase's acceptance tests, `FixtureCheck` as the `interact`
contract, `Attack.to_hit` / `damage` as the attack and damage formulas.
