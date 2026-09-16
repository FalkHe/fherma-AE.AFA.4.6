---
author: Falk Hermann <307901131+falkhetc@users.noreply.github.com>
owner: human
created: 2026-09-15
updated: 2026-09-15
stage: approved
---
# Decisions

One line each. `→ file` links an attachment in `decisions/`.

- D1: The SRD knowledge base is a self-contained module — ingestion, embedding and rules retrieval live behind it, and nothing outside it reaches the corpus directly.
- D2: Ingestion is driven from the command line only. There is no HTTP endpoint for it, and no other way in.
- D3: Ingest fetches SRD 5.1 from the CC-BY-4.0 markdown source, stores the file in the repository, and embeds from the stored file. A re-ingest does the same — fetch, store, embed — so a changed source shows up as a reviewable diff rather than a silent shift.
- D4: Every retrieved passage carries a reference good enough to cite the rule it came from, so we can always show which rules we acted on. The player-facing citation display is not built in this phase — it belongs to a later stage.
- D5: When a user creates a campaign and initiates an adventure playthrough, the SRD corpus is checked and the attempt fails with an error if it is empty. The game is never played against an empty corpus. This is the playthrough creation path (phase 5), not the hand-authored content JSON, which stays read-only in git. → [module-structure.md](decisions/module-structure.md)
- D6: The rules we act on are shown clearly in the UI, together with the CC-BY-4.0 attribution — a requirement the later citation-display stage inherits. The README states the attribution in this phase.
- D7: Retrieval applies a relevance floor — matches below it are not returned, so "no relevant rule" is a clean, distinguishable signal. The DM never invents or assumes a rule: where no passage comes back, it says so rather than stretching an unrelated one.
