---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 04

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The whole conversation: six new tools (`roll_scores`, `set_scores`, `set_skills`, `set_alignment`, `list_equipment_choices`, `pick_equipment`, `take_default_equipment`), class-skill auto-fill and the `point_buy` keyword in the builder, `render_seed` with item names, `ready_made_items` on the context filled by the CLI, the rewritten prompt step order, README, six new scripted tests | AC1 by-hand scores show "Points left" from the tool and a rolled set (scripted rng) lands on the sheet · AC2 second `set_identity` wins · AC3 two story skills plus class auto-fill on the Skills line · AC4 alignment in the header · AC5 `pick_equipment` and the default shortcut change the Equipment line · AC6 one sheet output carries alignment, skills and equipment | – |

One work item: the research split (rules/tools vs. tests) earns little, and the tests need the tools' exact wording. No qa work item (backlog: black-box tests only in sprint 05).

## Interfaces
- I1: the tool signatures, draft keys (`abilities`, `rolled`, `skills`, `alignment`, `equipment_pick_<i>`), `build_sheet(request, *, point_buy=True)`, `render_seed(seed, item_names=None)` and `CreationContext.ready_made_items` exactly as in `research.md → Interfaces`; technical decisions 1–9 are binding.
- I2: `CharacterCreateRequest` and the committed API schema stay untouched (rolled scores skip point buy through the keyword only).

## Order
WI1, then gates.
