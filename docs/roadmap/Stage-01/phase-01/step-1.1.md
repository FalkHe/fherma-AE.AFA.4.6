---
title: "Step 1.1 — The content module"
stage: 1
phase: 1
step: 1.1
status: spec
created: 2026-09-11
revised: 2026-09-11
---

# Step 1.1 — The content module

Build the `content` backend module: the Pydantic content schema, the
version-pinned loader, the referential rule set, the error types and the
`app content validate` command.

Read together with [`shared-knowledge.md`](shared-knowledge.md), which is the
**binding phase contract**. Every model name, field name, function signature,
rule number and message string in this step comes from it; where this file and
that file disagree, that file wins. You need to read nothing else — every
convention that matters to this step is restated below.

Runs **in parallel with step 1.2**. Step 1.2 touches only `docs/`; this step
touches only `backend/`. Neither may edit the other's files.

## 1. Scope

In scope:

- `backend/app/modules/content/` — `__init__.py`, `schemas.py`, `errors.py`,
  `service.py`, `commands.py`, `README.md`.
- Two added lines in `backend/app/cli.py`.

Out of scope, and a deviation if it appears:

- Any file under `backend/content/` — step 1.3 authors the campaign.
- Any file under `backend/tests/` — qa-backend owns the suite.
- Any file under `docs/` — step 1.2 owns the documentation.
- A `models.py`, a `routes.py`, an Alembic migration, a `Settings` field, an
  environment variable, an `ErrorCode`, an HTTP route, a frontend file.
- Any new entry in `backend/pyproject.toml`. Everything this step needs —
  `pydantic`, `typer`, the standard library's `json`, `pathlib` and `re` — is
  already declared.

## 2. Environment you will meet

- The Docker stack is **down**. No service is running.
- **`.env` exists**, copied from `.env.dist` and byte-identical to it;
  `.env.dist` stays owner-only and must not be edited. It has to exist, because
  `app content validate` otherwise raises a `pydantic` `ValidationError` before
  doing any work — `cli.py`'s callback calls `configure_logging()`, which calls
  `get_settings()`, and `Settings.database_url` has no default — and because
  `compose.yaml` declares `env_file: .env` on `app-cli`, so no `make` target can
  start a container without it. If it is missing, run `cp .env.dist .env`.
- Alembic head is `0001` (`backend/alembic/versions/0001_baseline.py`). **This
  step adds no migration.** Content is static JSON in git, never rows.
- `backend/app/modules/content/` does not exist.
- `backend/content/` does not exist, and will not until step 1.3. That is
  expected — see §7.
- `docs/modules/` does not exist; step 1.2 creates it.

## 3. Conventions this step must satisfy

Restated here so you do not have to hunt. All are landed decisions.

- **Modular by domain.** A module owns its own files under
  `backend/app/modules/<module>/`. `app/core/` is only for code with two or more
  module callers; nothing in this step earns a place there. `app/api/v1/router.py`
  is untouched — this module has no route.
- **Services are modules of functions, not classes.** No repository class, no
  loader class, no ORM anything.
- **Module-reference call style.** A caller does
  `from app.modules.content import service as content_service` and then
  `content_service.load_campaign(...)` / `content_service.CONTENT_ROOT`. **Never**
  `from .service import load_campaign` or `from .service import CONTENT_ROOT`:
  importing by name rebinds the object into the importing module and the test
  suite's `monkeypatch.setattr(service, ...)` then silently misses. This applies
  to the module's own `commands.py`.
- **Exported function names and signatures are contract.** qa-backend authors
  tests against §5 of the phase contract before this code exists. Changing a
  name, a parameter or a return type is a spec amendment, not an implementation
  choice.
- **Logs go to stderr; stdout is data only.** `configure_logging()` in
  `app/core/logging.py` already writes structlog to stderr. This command writes
  its result lines to stdout and its problem lines to stderr, and **emits no
  structlog record at the default level**.
- **Ruff, line length 100**, rule set `["E", "F", "I", "UP", "B", "SIM", "ASYNC"]`,
  target `py312`. Configured in `backend/pyproject.toml`; do not change it.
- **Python 3.12.** Use `X | None`, not `Optional[X]`.

## 4. Files this step creates or edits

All owned by **backend-dev**.

| File | Contents |
|---|---|
| `backend/app/modules/content/__init__.py` | Empty. |
| `backend/app/modules/content/schemas.py` | `ContentModel`, `ContentId`, `ProseText`, and the twelve models of phase contract §3, in that section's order. |
| `backend/app/modules/content/errors.py` | `ContentError`, `ContentNotFoundError`, `ContentInvalidError`, exactly as phase contract §6 gives them. |
| `backend/app/modules/content/service.py` | `CONTENT_ROOT`, `VERSION_PATTERN`, and the five public functions of phase contract §5, plus whatever private helpers the rule set needs. |
| `backend/app/modules/content/commands.py` | `content_app = typer.Typer()` and the `validate` command of phase contract §7. |
| `backend/app/modules/content/README.md` | Short module doc — Owns / Surface / Notes — in the shape of `backend/app/modules/users/README.md`. |
| `backend/app/cli.py` | Exactly two added lines (§5.5). |

## 5. The work

### 5.1 `schemas.py`

Implement phase contract §3 verbatim: `ContentModel` (`extra="forbid"`,
`frozen=True`), the `ContentId` and `ProseText` annotated aliases, and
`Abilities`, `Attack`, `StatBlock`, `Definition`, `Secret`, `CreaturePlacement`,
`Exit`, `Scene`, `Adventure`, `SeedCharacter`, `Campaign`, `LoadedCampaign`.

Points that are easy to get wrong and are contract:

- `StatBlock` is **required** on `Definition`, and `StatBlock.attacks` defaults
  to `[]`. There is no optional-stat-block branch anywhere.
- The JSON key is `character_class`, never `class`. No aliases, no alias
  generator, anywhere in this file.
- `armour_class`, not `armor_class`.
- Every human-readable string field is `ProseText`; never `str` with
  `Field(min_length=1)`.
- Every id field is `ContentId`.
- `Scene.truth` and `Adventure.scenes` and `Campaign.adventures` carry
  `Field(min_length=1)`; every other list defaults to empty.

### 5.2 `errors.py`

Phase contract §6, verbatim, including the `errors[0] if errors else "no detail"`
guard.

### 5.3 `service.py`

```python
CONTENT_ROOT: Path = Path(__file__).resolve().parents[3] / "content"
VERSION_PATTERN: re.Pattern[str] = re.compile(r"^v[0-9]+$")
```

`CONTENT_ROOT` is **read inside function bodies**, never captured as a default
argument value and never assigned to a module-level derived path — tests
repoint it with `monkeypatch.setattr`.

Implement `list_campaign_ids`, `list_versions`, `load_campaign`, `load_scene`,
`load_definition` with the signatures, return types and raise conditions of
phase contract §5. **There is no `latest_version`.**

`load_campaign` is the whole of the logic; `load_scene` and `load_definition`
are implemented over it and translate a missing key into
`ContentNotFoundError` with the exact `relative_path` of phase contract §6.1.

**Guard clause first, in every one of them** (phase contract §5.1): if
`campaign_id` does not match the `ContentId` pattern, or `version` does not match
`VERSION_PATTERN`, or — in `load_scene` / `load_definition` — the entity id does
not match `ContentId`, raise `ContentNotFoundError` with §6.1's pinned
`relative_path` **before any path is joined to `CONTENT_ROOT`**: no `Path`, no
`exists()`, no open. `list_versions` guards `campaign_id` likewise. A few lines
in each function, not a helper module and not a new dependency.

The walk:

0. If the version directory does not exist, raise
   `ContentNotFoundError(f"campaigns/{campaign_id}/{version}")` and stop. This
   happens **before** anything is read, so §6.1's pinned `relative_path` holds.
1. Read and validate `campaign.json`. If it is missing, unreadable, not valid
   JSON or schema-invalid, raise `ContentInvalidError` with that **one** entry
   and stop — nothing else can be located without its adventure list.
2. Read every `*.json` under `adventures/`, `scenes/` and `definitions/` by
   **globbing** (`(base / "scenes").glob("*.json")`), which yields nothing for a
   directory that does not exist. Never `iterdir()`, never `os.listdir`, never
   a bare `Path.exists()` branch — a missing directory must surface as R4/R7's
   referential failure, not as an `OSError`.
3. Non-`.json` files are ignored entirely: never read, never reported, never an
   orphan.
4. Any read, parse or schema failure on any of those files is **one `errors[]`
   entry and the walk continues** (phase contract §6.3).
5. De-duplicate `campaign.adventures` before evaluating anything downstream of
   it: a duplicate entry produces its `[R4]` entry and must not also produce a
   spurious `[R8]` double-claim.
6. Apply every rule of phase contract §11 marked `load` over whatever validated
   objects survived step 4. A rule that cannot be evaluated because its subject
   failed to load is simply not evaluated; its file already has an entry. Rules
   are also scoped to what is claimed: R6–R13 only for adventures listed in
   `campaign.adventures`, R9 and R11 only for scenes claimed by such an
   adventure — so one stray file produces one problem, not a cascade.
7. If `errors` is non-empty, sort it and raise
   `ContentInvalidError(campaign_id, version, errors)`. Otherwise return
   `LoadedCampaign`, with `adventures` keyed in `campaign.adventures` order.

Message grammar — phase contract §6.2, and this **is** the seam qa-backend
tests against:

```
<path relative to the version directory>: [<TAG>] <detail>
```

with `TAG` one of `READ`, `SCHEMA`, `R2`, or `R4`…`R18`. R1 has no tag of its
own — it is the readability and schema-validity of `campaign.json`, reported as
`[READ]` or `[SCHEMA]` — and **`[R3]` never appears in `errors[]`**, because R3
is a CLI check. For `SCHEMA`, the detail is
`".".join(str(p) for p in error["loc"])` + `": "` + `error["msg"]`, and when
`loc` is empty **both the location segment and its colon are omitted** — there
is never a `": : "` in any message. Paths use forward slashes and no leading
slash.

R8 and R17 must name deterministic files when a conflict involves several:
R8's double-claim names the **second** adventure in `campaign.adventures` order,
and R17 names **every colliding definition after the first** in sorted-id
order — for the two-definition case, the second.

### 5.4 `commands.py`

```python
import typer
from app.modules.content import service as content_service

content_app = typer.Typer()


@content_app.command("validate")
def validate() -> None: ...
```

Read `content_service.CONTENT_ROOT` and `content_service.VERSION_PATTERN`
**inside the command body**. An import-time `from ... import CONTENT_ROOT`
would bind the real path and make every CLI test run against the shipped tree.

Behaviour, from phase contract §7:

- Walk `content_service.list_campaign_ids()`. For each campaign, list its
  subdirectories directly and, for every name that `VERSION_PATTERN` does not
  match, write
  `<campaign_id>/<name>: [R3] version directory name must match ^v[0-9]+$` to
  **stderr** and mark the run failed. Then call
  `content_service.list_versions()` and `load_campaign` for each conformant
  version.
- A valid version writes `<campaign_id>/<version>: ok` to **stdout**.
- A `ContentInvalidError` writes one stderr line per entry of `.errors`, each
  prefixed `<campaign_id>/<version>: `.
- A campaign with no conformant version directory at all: write
  `<campaign_id>: no version directory found` to stderr and fail.
- No campaign at all: write `no campaigns found under <CONTENT_ROOT>` to stderr
  and fail.
- Exit `0` only if at least one campaign version was found, every one was valid,
  no non-conformant version directory exists and every campaign has at least one
  conformant version. Otherwise exit `1` (`raise typer.Exit(code=1)`).
- The command defines **no** output for a `ContentNotFoundError`: neither raiser
  can fire inside its own walk, since it only names campaigns and versions it has
  just listed. Do not add a handler for one.
- Write **no structlog record** at the default level. Use `typer.echo(...)` /
  `typer.echo(..., err=True)` for every line.

### 5.5 `cli.py`

Append below the existing `openapi` block, and change nothing else in the file:

```python
from app.modules.content.commands import content_app

cli.add_typer(content_app, name="content")
```

The import goes with the other imports at the top; the `add_typer` call goes at
the end of the file. The `openapi` sub-app stays first and stays inline.

### 5.6 `README.md`

Owns / Surface / Notes, roughly twenty lines, in the shape of
`backend/app/modules/users/README.md`. It **links** to `docs/modules/content.md`
for the field reference rather than repeating it. That file is being written in
parallel by step 1.2; link to it anyway.

## 6. Acceptance criteria

Numbered, each provable or refutable by qa-backend without reading the
implementation. Unless stated otherwise, "a tree" means a content tree built in
`tmp_path` with `monkeypatch.setattr(service, "CONTENT_ROOT", tmp_path)`, and a
"valid tree" means the worked example of phase contract §4.1.

### Schema

1. `Definition` rejects a payload with no `stat_block`.
2. `StatBlock` accepts a payload with no `attacks` key and yields
   `attacks == []`.
3. Every model rejects an unknown key (`extra="forbid"`) — provable on at least
   `Scene`, `Definition` and `SeedCharacter`.
4. A `SeedCharacter` payload using the key `class` instead of `character_class`
   is rejected.
5. A `ProseText` field given `"   "` is rejected; given `"  a  "` it validates
   and the stored value is `"a"`.
6. A `ContentId` field rejects `"Mill_Floor"`, `"mill floor"` and `""`, and
   accepts `"mill-floor"`.
7. `Abilities` rejects a payload missing any one of the six scores, and rejects
   `0` and `31`.
8. A `ContentModel` instance rejects attribute assignment (`frozen=True`).

### Loading

9. `load_campaign` over the §4.1 worked example returns a `LoadedCampaign` whose
   `version` is the version string passed in, whose `adventures` keys are
   `campaign.adventures` in that order, whose `scenes` holds every scene of every
   adventure, and whose `definitions` holds every definition file.
10. `load_scene(campaign_id, version, "mill-floor")` over the valid tree returns
    that `Scene`; `load_definition(..., "bog-lurker")` returns that `Definition`.
11. `list_campaign_ids()` returns the campaign directory names sorted, and
    returns `[]` when `campaigns/` does not exist, raising nothing.
12. `list_versions()` returns conformant version names sorted by numeric suffix
    ascending (`v2` before `v10`), omits non-conformant names, and raises
    `ContentNotFoundError` for an unknown campaign with
    `relative_path == "campaigns/<campaign_id>"`.
13. `load_campaign` for a missing version directory raises `ContentNotFoundError`
    with `relative_path == "campaigns/<campaign_id>/<version>"`.
14. `load_scene` for an unknown scene id over an otherwise valid tree raises
    `ContentNotFoundError` with
    `relative_path == "campaigns/<campaign_id>/<version>/scenes/<scene_id>.json"`;
    `load_definition` likewise with `.../definitions/<definition_id>.json`.
15. A non-`.json` file placed in `scenes/` (e.g. `notes.md`) changes nothing:
    the valid tree still loads and no error mentions it.
16. Deleting the `definitions/` directory from a tree that references a
    definition produces an `[R14]` entry, not an `OSError` or a traceback.
17. **No id argument reaches the filesystem unvalidated** (phase contract §5.1).
    `load_campaign("../x", "v1")`, `load_campaign("hollow-reach", "../v1")` and
    `load_scene("hollow-reach", "v1", "../campaign")` each raise
    `ContentNotFoundError` carrying §6.1's pinned `relative_path`, and nothing
    outside `CONTENT_ROOT` is read — provable by pointing `CONTENT_ROOT` at a
    `tmp_path` subdirectory with a readable file beside it and asserting the
    raise, with no `ContentInvalidError` and no file content returned.

### Error reporting

18. Every entry of `ContentInvalidError.errors` matches
    `^[^:]+(/[^:]+)*: \[(READ|SCHEMA|R2|R([4-9]|1[0-8]))\] .+$` — a
    version-directory-relative path, a bracketed tag, a non-empty detail.
19. `errors` is sorted ascending as strings, and two loads of the same broken
    tree produce identical lists.
20. A tree with a broken scene **and** a broken definition produces **both**
    entries from one call — the walk does not abort on the first.
21. A tree whose `campaign.json` is malformed JSON produces exactly **one**
    entry, tagged `[READ]`, naming `campaign.json`, and no entry for any other
    file.
22. A tree whose `campaign.json` is schema-invalid produces exactly one entry,
    tagged `[SCHEMA]`.
23. A model-level Pydantic failure (e.g. a scene file containing a JSON array
    rather than an object) yields a `[SCHEMA]` message containing no `": : "`
    and no empty location segment.
24. `ContentInvalidError`'s `str()` contains the campaign id, the version and
    the problem count, and constructing one with `errors=[]` does not raise.

### The referential rules — one criterion per rule

Each is proved by mutating the §4.1 worked example in exactly the way named,
loading, and asserting that `errors` contains an entry whose tag is the rule's
and whose path is the file phase contract §11 says it names. **The assertion is
on the path and the tag, never on the detail wording.**

25. **R1** — delete `campaign.json` → `campaign.json: [READ] …` and nothing else.
26. **R2** — set `campaign.id` to `"wrong-id"` → `campaign.json: [R2] …`.
27. **R4** — add `"no-such-adventure"` to `campaign.adventures` →
    `campaign.json: [R4] …`; and listing `"the-sunken-mill"` twice produces an
    `[R4]` entry **and no `[R8]` entry**, because the list is de-duplicated
    before any later rule runs.
28. **R5** — add `adventures/orphan.json` (schema-valid, unlisted) →
    `adventures/orphan.json: [R5] …`.
29. **R6** — set the adventure file's `id` to `"other"` →
    `adventures/the-sunken-mill.json: [R6] …`.
30. **R7** — add `"no-such-scene"` to the adventure's `scenes` →
    `adventures/the-sunken-mill.json: [R7] …`; a duplicate entry in `scenes`
    likewise.
31. **R8** — add `scenes/orphan.json` unclaimed by any adventure →
    `scenes/orphan.json: [R8] …`. With two adventures both claiming
    `mill-floor`, the entry names the **second** adventure file in
    `campaign.adventures` order.
32. **R9** — set `scenes/mill-floor.json`'s `id` to `"other"` →
    `scenes/mill-floor.json: [R9] …`.
33. **R10** — set `entry_scene` to a scene id not in the adventure's `scenes` →
    `adventures/the-sunken-mill.json: [R10] …`.
34. **R11** — point `mill-approach`'s exit at `"under-whee"` →
    `scenes/mill-approach.json: [R11] …`; an exit whose `to` is
    `"mill-approach"` itself likewise; an exit pointing at a scene that exists
    but belongs to a different adventure likewise.
35. **R12** — give `mill-floor` an exit back to `mill-approach`, so no scene is
    terminal → `adventures/the-sunken-mill.json: [R12] …`.
36. **R13** — add a third scene listed in the adventure but reachable from no
    exit → `adventures/the-sunken-mill.json: [R13] …`. A scene reachable only
    through an exit carrying a `condition` **is** reachable and produces no
    entry. An adventure of exactly one scene, which is its `entry_scene` and has
    no exits, produces no `[R13]` entry — the entry scene counts as reached with
    no exits traversed.
37. **R14** — set `mill-floor`'s placement `definition` to `"no-such-thing"` →
    `scenes/mill-floor.json: [R14] …`.
38. **R15** — set `definitions/bog-lurker.json`'s `id` to `"other"` →
    `definitions/bog-lurker.json: [R15] …`.
39. **R16** — add `definitions/unused.json` referenced by no scene →
    `definitions/unused.json: [R16] …`.
40. **R17** — add a second definition whose `name` is also `"Bog Lurker"` → an
    `[R17]` entry naming the second definition file in sorted-id order. A second
    definition named `"bog lurker"` produces the same entry: the comparison is
    case-insensitive, after stripping. A *third* colliding definition produces a
    third entry — every colliding definition after the first is reported.
41. **R18** — give `mill-floor` two `creatures` entries for `bog-lurker` →
    `scenes/mill-floor.json: [R18] …`.

### The CLI

**Which app each assertion drives is contract.** Criteria 42–48 are asserted via
`CliRunner().invoke(content_app, [])` — **with an empty argument list, carrying
no `"validate"`**, because Typer collapses a single-command app, so
`content_app` *is* the command and the name `validate` exists only through the
`cli` group (passing it yields Click's `UsageError` and exit code 2).
**Criterion 49 is asserted via `CliRunner().invoke(cli, ["content",
"validate"])`** — `content_app` has no callback, so `configure_logging()` runs
on that path only, and an assertion made against `content_app` would pass for
any implementation. Criterion 50 drives `cli` by nature.

42. `app content validate` over a tree containing only the §4.1 worked example
    exits `0`, writes `hollow-reach/v1: ok` to stdout and nothing to stderr.
    **Stdout is compared after `.strip()`** — a trailing newline is not part of
    the contract; the line content is.
43. Over a tree with one broken campaign version it exits `1`, writes nothing
    to stdout for that version, and writes one stderr line per
    `ContentInvalidError.errors` entry, each prefixed `<campaign_id>/<version>: `.
44. With two campaign versions, one valid and one broken, it exits `1`, the
    valid one still appears on stdout, and the broken one's problems appear on
    stderr.
45. Over a `CONTENT_ROOT` with no `campaigns/` directory, or with an empty one,
    it exits `1` and writes `no campaigns found under <CONTENT_ROOT>` to stderr.
46. A campaign directory containing a version directory named `v1.0` (alongside
    a valid `v1`) makes the command exit `1` and write
    `<campaign_id>/v1.0: [R3] version directory name must match ^v[0-9]+$` to
    stderr, while `<campaign_id>/v1: ok` still reaches stdout.
47. A campaign directory holding no version directory at all, or only
    non-conformant ones, makes the command exit `1` and write
    `<campaign_id>: no version directory found` to stderr.
48. `monkeypatch.setattr(service, "CONTENT_ROOT", tmp_path)` changes what the
    **CLI** validates — i.e. the command reads the attribute at call time, not
    at import.
49. Driven as `CliRunner().invoke(cli, ["content", "validate"])` over a broken
    tree: no line the command writes to **stderr** carries a structlog timestamp
    or level prefix at the default log level, and **stdout** carries no log
    record at all — an unconfigured structlog `PrintLogger` writes to stdout,
    which criterion 42's stream split would otherwise fail on silently.
50. `app --help` lists a `content` command group, and `app content --help` lists
    `validate`. `app openapi export` still prints parseable JSON and only JSON
    to stdout.

## 7. What this step does **not** have to satisfy

`backend/content/` does not exist while this step is being built. Therefore:

- Every test in this step repoints `CONTENT_ROOT` at a `tmp_path` tree.
- **No criterion above concerns the real `backend/content/` tree.** The unmocked
  shipped-tree test, and the assertion that `app content validate` exits `0`
  against the repository as checked out, belong to **step 1.3**.
- Running `app content validate` by hand in this step will exit `1` with
  `no campaigns found` — that is criterion 45 passing, not a defect.

## 8. Static checks the dev agent runs

Run these and only these. **Do not run pytest** — the suite belongs to
qa-backend.

```bash
cp .env.dist .env                      # once, if not already done
docker compose run --rm --no-deps app-cli ruff check .
docker compose run --rm --no-deps app-cli ruff format --check .
docker compose run --rm --no-deps app-cli python -c "from app.main import create_app; create_app()"
docker compose run --rm --no-deps app-cli app content validate; echo "exit=$?"
docker compose run --rm --no-deps app-cli app openapi export > /dev/null
```

Expected: ruff clean; the app constructs; `app content validate` exits `1` with
`no campaigns found under /app/content` on stderr and nothing on stdout;
`app openapi export` still succeeds. The host ruff equivalents (`cd backend &&
uv run ruff check .`, `uv run ruff format --check .`) are acceptable if uv is
installed. **There is no host fallback for `app content validate`**: `Settings`
pins `env_file=".env"` relative to the working directory and `backend/.env` does
not exist, so run that check in `app-cli` as given.

**No Alembic round-trip is required: this step adds no migration.**

## 9. The parallelisation split

| Agent | Owns |
|---|---|
| backend-dev | `backend/app/modules/content/**`, and the two added lines in `backend/app/cli.py`. Nothing else. |
| qa-backend | `backend/tests/content/**`. Authors the suite from this spec and the phase contract before the code exists (mode A), then runs it against the landed code (mode B). |

Read-only for both: [`shared-knowledge.md`](shared-knowledge.md),
`backend/app/modules/users/` and `backend/app/modules/auth/` as the shape a
module takes, `backend/tests/conftest.py` and `backend/tests/test_cli.py` as the
shape a test file takes.

**backend-dev must not create or edit any file under `backend/tests/`, under
`docs/`, or under `backend/content/`. qa-backend must not edit any file under
`backend/app/`.**

## 10. Deviation clause

**Zero deviations from this spec and from
[`shared-knowledge.md`](shared-knowledge.md).** If a deviation seems necessary —
a signature that cannot be implemented as written, a rule that cannot be
evaluated, a message grammar that does not fit a real case — **stop and report
it**. Do not improvise a different name, a different tag, an extra field, an
extra function or an extra file.
