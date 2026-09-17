---
author: Falk Hermann <307901131+falkhetc@users.noreply.github.com>
owner: human
created: 2026-09-16
updated: 2026-09-16
stage: approved
---
# Decisions

One line each. `→ file` links an attachment in `decisions/`.

- D1: A user may hold several campaign runs at once, including more than one of the same campaign — each is independent, so the list has to distinguish two entries carrying the same campaign title.
- D2: The two state entities are `campaign_run` and `adventure_run` — neither is called "playthrough". Player-facing wording is i18n-only and is decided in the UI phase; no model or state term follows from it.
- D3: A campaign run is active, archived or finished. Archived is the player setting it aside and is reversible; finished is reached by playing the campaign to its end and is not resumable. Nothing is ever deleted — the event stream and the cost record survive.
- D4: The player sees only the story thread — narration, their own actions, visible rolls. Hidden events are recorded but never shown and leave no visible gap. Cost is recorded per event and reportable to the owner, never displayed to the player.
- D5: A campaign run lives at a reloadable URL, and resuming is exactly reloading that page — the visible event stream is the transcript, replayed as it stands, with play continuing at its end. No recap, no extra stored state.
- D6: The four per-run overrides (model, temperature, personality prompt, system-prompt override) stay NULL in Stage-01 and fall back to the app defaults. The columns exist so a later phase can fill them without a migration; there is no player-facing setting yet.
- D7: The pinned content version is invisible to the player. A running campaign run keeps playing the version it started on; new content is reached only by starting a new one.
- D8: This phase builds no combat-specific state — no encounter, no initiative. What a fight is to the player, and whatever state that needs, is decided in the DM-turn phase (8); the general docs mark the turn-order promise as deferred, not delivered.
- D9: A table is proven by the migration running against the dev database during implementation, and schema drift surfaces through the model tests. Superseded in part by D15: this phase builds no fixture of its own, but it does reuse the one that has since landed.
- D10: State has two levels, because a campaign is only a grouping and cannot be played while an adventure can. The campaign run is the container — ownership, the content-version pin, settings, status, the objects and the event stream. The adventure run is one adventure being played, one row per adventure entered, recording when it was entered and whether it is done. The schema is prepared for a campaign of several adventures from the start. → [model.md](decisions/model.md)
- D11: A campaign run carries a nullable title. Empty means the list shows the campaign name plus the creation date; the owner can set a title of their own at any time.
- D12: Position belongs to the creature, not the party — two characters may stand in different scenes, as at a real table where the DM cuts between a split party. The model is prepared for several players in one campaign run from the start; Stage-01 still ships single-player.
- D13: The model lets a user control several characters in one campaign run; Stage-01 gameplay assumes exactly one. A player-character object references its player through the membership row, and no unique index restricts the count.
- D14: One module, `playthrough`, holds the game state and the mutations that change it — the five tables plus the phase-5 transitions. `game` stays separate as the agent's home, and imports run `game` → `playthrough`, never the reverse.
- D15: Phase 3 reuses the real-database test fixture SRD shipped (`backend/tests/srd/conftest.py`), promoted to a shared fixture because a second module now needs it unchanged. Each sprint's accept/refuse criteria run as real database tests under `make backend-test-db`, so every constraint stays proven rather than being checked by hand once.
