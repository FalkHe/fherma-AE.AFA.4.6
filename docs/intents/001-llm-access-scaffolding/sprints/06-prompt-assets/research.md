---
author: fhit:architect
owner: agent
created: 2026-09-16
---
# Research: sprint 06 — a prompt resolves by id at a named version

## Facts

**The ruling holds.** `docs/general/model.md:271` still reads "Prompts live in the module that uses them, versioned in
git"; `:247` still pins `modules/game/prompts/` as the *only* root — the logged error owned by **this phase**
(`docs/roadmap/Stage-01/README.md:333`; corrected `:83`-`84`, "there is no single prompt root"). `model.md:92`-`95`:
personality is referenced *by prompt id, never as stored text*, so the seam returns text plus a version string.

**Version granularity is not open.** A version is a whole `v<n>` snapshot, never edited in place (`model.md:87`-`88`),
and D5 pins the prompt version *the way it pins the content version* — one identifier per tree. So `v<n>` sits
**above** kind/id: phase 5 pins one string per capability, phase 10's composition is consistent, no fallback.

**The precedent, `content`.** *Copy*: module-level root constant (`…/content/service.py:16`), `^v[0-9]+$` (`:17`), id
regex `^[a-z0-9]+(-[a-z0-9]+)*$` (`:19`), numeric sort `int(v[1:])` (`:69`), the `NotFound`/`Invalid` pair
(`…/content/errors.py:5`,`:11`), and the Typer shape (`…/content/commands.py:6`,`:16`-`17`: one `typer.Typer()`,
failures to stderr, `typer.Exit`), wired like `backend/app/cli.py:27`-`28`. *Differ twice*:
content raises **NotFound for a malformed id** (`service.py:74`-`75`), which AC4 forbids; and its `Invalid` means
"schema validation failed", where here it means "malformed id". *Share nothing*: the overlap is four regex lines plus a
sort key, and extracting it would promote with one module caller, against AGENTS.md's "a helper is promoted to `core/`
only once a **second** module calls it, unchanged", coupling two error taxonomies — while importing
`app.modules.content.service` is forbidden outright ("one module never imports another module's internals").

**Home: `backend/app/core/prompts/`,** sibling to `core/llm/` — the landed precedent for a seam in `core/` with its own
`commands.py`. Not a module: the resolver is cross-capability by construction, so any module home forces module→module
imports; and the second-caller rule governs *promoting* an existing module helper, where this is new,
shared-by-definition code. Consumers: phase 7's character agent and phase 8's DM each do
`from app.core.prompts import service` → `service.load_prompt(...)`. No `game` or `character` module exists yet.

**Tests.** CliRunner with split stdout/stderr (`backend/tests/content/test_cli.py:26`,`:34`-`36`); repoint the root via
`monkeypatch.setattr(service, "PROMPT_MODULES_ROOT", tmp_path)` — the module attribute, never the imported name
(`backend/tests/content/conftest.py:289`-`294`); shipped-tree guard `…/content/test_shipped_tree.py:1`-`13`. No DB, key
or network, so AC5 is free. Stdlib only, no new dependency; typer 0.27.2 (`backend/uv.lock:916`) and its `CliRunner`
are already used in-repo, so nothing rests on an unverified external API.

## Work items

- **WI1 resolver** — `backend/app/core/prompts/{__init__,errors,service}.py` per Interfaces; tests
  `backend/tests/core/prompts/{__init__,conftest,test_service}.py` over a `tmp_path` tree: grammar, traversal refusal,
  highest version, no fallback, both error classes.
- **WI2 CLI** — `backend/app/core/prompts/commands.py` + `cli.add_typer(prompt_app, name="prompt")` in
  `backend/app/cli.py`; `backend/tests/core/prompts/test_cli.py` for AC1–AC4 (verbatim stdout, version line, exits
  0/2/3). Parallel with WI1 against the fixed signatures.
- **WI3 seed + guard** — `backend/app/modules/game/prompts/v1/system/smoke.md`, 2–3 lines naming itself the resolution
  fixture (**no DM content**; phase 8 owns `system/dm.md`), creating `modules/game/` as a **prompts-only directory: no
  Python, no `backend/tests/game/`**. Guard `backend/tests/core/prompts/test_shipped_prompts.py`: every file under
  `app/modules/*/prompts/` is `.md`, sits at `<capability>/prompts/v<n>/<kind>/<id>.md` and resolves. Parallel.
- **WI4 doc correction** — `docs/general/model.md`: tree `:247`-`251` becomes
  `…/modules/<capability>/prompts/v<n>/<kind>/<id>.md`, `:271` states the convention; closes register entry `…:333`.

## Interfaces

**Path.** `PROMPT_MODULES_ROOT: Path = Path(__file__).resolve().parents[2] / "modules"` (from
`app/core/prompts/service.py`) → `<root>/<capability>/prompts/<version>/<kind>/<id>.md`.

**Grammar.** Split the id on `/` into **exactly three** segments, each matching
`_SEGMENT = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")`; `VERSION_PATTERN = re.compile(r"^v[0-9]+$")`. A segment admits no
`.`, `/`, empty string, uppercase or edge hyphen, so `..`, `a/../b` and absolute paths are **unrepresentable**: refusal
is by whitelist before any `Path` is built — no `resolve()` containment check, and none needed.

```python
@dataclass(frozen=True)
class ResolvedPrompt:
    prompt_id: str; capability: str; kind: str; name: str   # name = third segment
    version: str; text: str; path: Path                     # text verbatim, unmodified

def parse_prompt_id(prompt_id: str) -> tuple[str, str, str]       # raises PromptIdInvalidError
def list_versions(capability: str) -> list[str]                   # ascending int(v[1:]); [] if absent
def load_prompt(prompt_id: str, *, version: str | None = None) -> ResolvedPrompt
```

`version=None` → highest of `list_versions(capability)`; empty → NotFound. **No run-side pinning here**;
`ResolvedPrompt.version` is the entire seam phase 5 consumes.

**Errors** (`core/prompts/errors.py`, shaped like `content/errors.py:5`,`:11`): `PromptError` base;
`PromptIdInvalidError(value: str, reason: str)`, `code = "PROMPT_ID_INVALID"`; `PromptNotFoundError(relative_path:
str)`, `code = "PROMPT_NOT_FOUND"`. *Invalid* ⇔ not three well-formed segments, or `--version` fails
`VERSION_PATTERN`; *NotFound* ⇔ well-formed, but capability dir, `prompts/`, version dir or `<id>.md` is missing.
Neither joins `core/errors.ErrorCode` — no route exists, and `content` does the same (`app/core/errors.py:17`-`34`).

**CLI.** `app prompt show <capability>/<kind>/<id> [--version v<n>]`. Success: **stdout = the file text verbatim and
nothing else** (AC1: `… | diff - <file>` passes); **stderr = `resolved: <prompt_id> <version>`** (AC3 — both reach the
terminal together); exit `0`. NotFound → stderr `not found: <relative_path> [PROMPT_NOT_FOUND]`, exit **3**. Invalid →
stderr `invalid prompt id: <value> (<reason>) [PROMPT_ID_INVALID]`, exit **2** — codes in the text, so a test asserts
code and exit status independently. A single-stream form, if ever wanted, is a later `--json`.

## Open questions

- **None product-visible; the sprint is not blocked.** Judged: neither the file format nor the id grammar is
  product-visible — a player sees neither, and phase 10's dev drawer shows ids, which this sprint does not change.
- *agent's call, vetoable* — **plain Markdown, no frontmatter**: AC1's "verbatim" forbids stripping a header, and the
  only metadata a prompt might carry (model, temperature) lives on the run (`model.md:92`). Phase 10 stays open —
  composition concatenates resolved ids; metadata, if ever needed, lands in a sibling file. Segments: lowercase-kebab.
- *technical* — the seed pre-creates phase 8's `modules/game/` directory with no code in it; the alternative puts a
  prompt in a module that owns none. Recommend `game`; a reviewer may move the file without touching the resolver.
