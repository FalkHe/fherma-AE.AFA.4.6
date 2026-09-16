---
author: sprint
owner: agent
created: 2026-09-16
---
# Plan: Sprint 06 — a prompt resolves by id at a named version

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | A resolver that turns an id plus optional version into prompt text and the version it came from | grammar accepts exactly three kebab segments; traversal is unrepresentable; highest version wins numerically; a missing version never falls back; both error classes raised for their own cause | I1 |
| 2 | backend-python | `app prompt show` prints the text verbatim and says which version it resolved | text on stdout and nothing else; the resolved line on stderr; exits 0 / 2 / 3 for success, invalid, not-found | I2 · I1 |
| 3 | backend-python | One seed prompt that proves resolution, and a guard over everything shipped | every file under `app/modules/*/prompts/` is `.md`, sits at the canonical path and actually resolves | I1 |
| 4 | backend-python | `docs/general/model.md` describes the real prompt layout | – (markdown only) | – |
| qa | qa | Black-box acceptance tests for AC1–AC5 | over a `tmp_path` tree and through the real CLI, no network, no DB | I1, I2 |

## Interfaces
Verbatim from `research.md → Interfaces`; binding. Summarised — read that file for the full text.

- I1: `backend/app/core/prompts/` — `PROMPT_MODULES_ROOT` resolving to `backend/app/modules`, and the layout `<capability>/prompts/<version>/<kind>/<id>.md`. Grammar: split on `/` into **exactly three** segments each matching `^[a-z0-9]+(-[a-z0-9]+)*$`; `VERSION_PATTERN = ^v[0-9]+$`. Frozen `ResolvedPrompt(prompt_id, capability, kind, name, version, text, path)` with `text` verbatim. `parse_prompt_id(...)`, `list_versions(capability)` ascending by `int(v[1:])`, `load_prompt(prompt_id, *, version=None)`. Errors in `core/prompts/errors.py`: `PromptError` base, `PromptIdInvalidError(value, reason)` with `code = "PROMPT_ID_INVALID"`, `PromptNotFoundError(relative_path)` with `code = "PROMPT_NOT_FOUND"`. Neither joins `core/errors.ErrorCode` — no route exists, and `content` does the same.
- I2: `app prompt show <capability>/<kind>/<id> [--version v<n>]`, registered `cli.add_typer(prompt_app, name="prompt")`. **stdout is the file text verbatim and nothing else**, so `app prompt show … | diff - <file>` passes. **stderr carries `resolved: <prompt_id> <version>`.** Exit 0 success, 2 invalid id or bad `--version`, 3 not found; the code string appears in the stderr text so a test can assert code and exit status independently.

## Acceptance tests (qa)
- AC1 → a prompt under its owning module's `prompts/` resolves and prints verbatim, byte for byte.
- AC2 → `--version v1` prints that version; with no flag the **numerically** highest resolves (`v10` beats `v9`).
- AC3 → the resolved version identifier reaches the terminal alongside the text, so a run could record it.
- AC4 → an unknown id and a malformed id fail **differently** — different codes, different exit statuses, both non-zero.
- AC5 → all of it runs with no API key and no database; this sprint touches neither.

## Order
All four work items and qa run in parallel; WI2, WI3 and qa code against I1's fixed signatures.

**Three judgement calls, recorded for veto:**
1. The resolver lives in `core/prompts/`, not a module. It is cross-capability by construction, so any module home would force module→module imports, which `AGENTS.md` forbids. The second-caller rule governs *promoting* an existing helper, not placing new shared code.
2. **Deliberate duplication.** `content/service.py` resolves ids against versioned directories too, but nothing is shared — four regex lines are duplicated on purpose rather than extracting a premature abstraction, and this sprint diverges from `content` in one place: `content` raises NotFound for a malformed id, whereas AC4 requires the two to differ.
3. Plain Markdown, no frontmatter. AC1's "verbatim" forbids stripping a header, and the only metadata a prompt might carry lives on the run. Phase 10's composition stays possible: it concatenates resolved ids.
