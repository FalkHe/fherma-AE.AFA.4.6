# Prompt-system refactoring

Status: proposed; no implementation has been made.

## Objective

Version each prompt independently. A prompt version belongs in the filename,
using an exactly two-digit number:

```text
backend/app/modules/game/prompts/system/dm.v01.md
backend/app/modules/game/prompts/system/dm.v02.md
backend/app/modules/game/prompts/system/smoke.v01.md
```

The stable prompt ID remains `<capability>/<kind>/<name>`, for example
`game/system/dm`. The version is not part of that ID.

The canonical layout becomes:

```text
backend/app/modules/<capability>/prompts/<kind>/<name>.v<NN>.md
```

`NN` is exactly two decimal digits. Versions run from `v01` through `v99`
(`v00` is invalid) and are compared numerically; `v02` is newer than `v01`.

## Why change it

The current layout versions the complete prompt tree for a capability:

```text
backend/app/modules/<capability>/prompts/v<n>/<kind>/<name>.md
```

The resolver first selects the newest capability version and then looks for
the requested prompt inside it. Consequently, adding one prompt to a new
capability version also changes resolution for every other prompt. Because the
resolver deliberately has no fallback, all unchanged prompts must be copied
into the new directory or they become unavailable through default resolution.

Prompts are expected to evolve independently. Filename-level versions remove
that coupling and avoid duplicating unchanged prompt files.

## Intended resolver behaviour

The existing call shape should remain stable:

```python
load_prompt("game/system/dm")
load_prompt("game/system/dm", version="v01")
```

- Without `version`, resolve the numerically highest version of that specific
  prompt.
- With `version`, resolve only the requested file and never fall back.
- Return the resolved two-digit version in `ResolvedPrompt.version`.
- Preserve prompt contents byte-for-byte as the current resolver does.
- Keep the existing prompt-ID grammar and traversal protection.
- Make version discovery prompt-specific, for example
  `list_versions("game/system/dm")`, instead of capability-specific.
- Keep the CLI contract `app prompt show <prompt-id> [--version vNN]`.

## Run pinning and composition

The existing design says that a campaign run pins one prompt version for a
whole capability. That assumption must change with per-prompt versioning.

When an agent composes multiple prompts, the run should eventually retain each
resolved `(prompt_id, version)` pair. This ensures that an existing playthrough
does not silently adopt a newer DM, personality, or other component prompt.
The current `CampaignRun` model does not yet persist a prompt version, so there
is no stored prompt-version data to migrate at present.

## Implementation scope

When approved for implementation, the refactoring consists of:

1. Move shipped prompts from `prompts/v1/<kind>/<name>.md` to
   `prompts/<kind>/<name>.v01.md`.
2. Change prompt-specific version discovery and path construction in
   `core/prompts/service.py`.
3. Require the explicit version format `vNN` rather than `v<n>`.
4. Update resolver, CLI, acceptance, and shipped-tree guard tests.
5. Update module and system documentation that declares the old layout.
6. Revisit D5 before run-side prompt pinning is implemented, replacing one
   capability version with the set of resolved prompt/version pairs.

Most prompt consumers should require no change because `load_prompt()` can
retain its current interface. The principal compatibility break is the asset
layout and the accepted version syntax: callers using `version="v1"` must use
`version="v01"`.

## Out of scope

- Changing prompt contents.
- Moving prompt resolution into `core/llm`; prompt storage and model access
  remain separate concerns.
- Adding fallback between versions.
- Implementing run-side prompt pinning as part of the filesystem refactoring.
