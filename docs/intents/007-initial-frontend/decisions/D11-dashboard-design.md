---
author: Falk Hermann <307901131+falkhetc@users.noreply.github.com>
owner: human
created: 2026-09-19
updated: 2026-09-19
---
# D11 — Dashboard and run screen design

**Source:** `docs/design/dnd-app-dashboard-design/` (Claude Design handoff bundle).
`project/Dashboard.dc.html` is the dashboard with the select dialog, `project/CampaignRun.dc.html`
the campaign-run screen, `project/_ds/…/readme.md` the design system ("Goblin Pub"). The page
`project/SessionView.dc.html` is the play screen and is **not** part of this intent.

The design is the visual truth: recreate its layout, spacing, colours and states. Where the design
shows data the product does not have, the rules below apply.

## Dashboard

| Design element | Product |
|---|---|
| Header wordmark "Goblin Pub" | "The Goblin's Tavern" (D14) |
| Account button → menu with name, e-mail, "Sign out" | as designed |
| "Welcome back, <name>." + one-line subtitle | as designed; subtitle counts the player's runs in plain words |
| Tags "In progress / New / Archived" | as designed; "New" = run not yet started, "In progress" = an adventure was entered, "Archived" = archived (D3). Default tag per D12 |
| Archived note "Archived campaigns stay hidden until you unarchive them…" | reworded: no unarchive exists — the note says archived runs are kept, view-only |
| Run card: art slot, title, status badge, teaser, meta, button | cover-art **placeholder** (no art exists); title and teaser = campaign title and summary; meta = "Adventure n of m · 1 player · Created <relative date>" (D11); button "Begin" for new runs, "Resume" for in-progress runs, both open the run screen; archived cards have no button |
| "Start a new campaign" card with "Create new campaign" | as designed (D8) |
| Empty state | not in the design; D8 wording, styled like the CTA card |

## Select dialog

| Design element | Product |
|---|---|
| Title "Select a campaign", intro "Choose the story your party will play. You can rename it later." | intro shortened to "Choose the story your party will play." — no rename in this intent (ASSUMPTION) |
| Catalogue card: cover art, title, teaser, "N adventures", tone badge | art **placeholder**; title, summary and adventure count from the catalogue; **no tone badge** — content has no tone (ASSUMPTION: omit rather than invent) |
| Creating state "Rolling up "<title>" — taking you to the table." | as designed, then straight to the run screen (D10) |

## Campaign-run screen

| Design element | Product |
|---|---|
| Back link "Campaigns", account avatar | as designed |
| Status badge, campaign title, description | badge = run status; title/description = campaign title and summary |
| "PARTY" + "n of m characters ready" | as designed; one player (the owner) until sharing exists (D2) |
| Player card: initial, name, role badge, e-mail, state box, "Create character" | as designed; state box "No character yet" or the character's name; button opens the in-development dialog (D4, D13) |
| "Invite a player · Up to six at the table" tile | stays; opens the in-development dialog (D13) |
| "ADVENTURES": numeral, title, badge, teaser, action | teaser = adventure intro (first sentence or a clipped excerpt); badges and button per D9; "Start adventure" disabled until the adventure-entry intent (D1) |

## Consequences for the backend additions (D1)

- Campaign catalogue must return, per campaign: id, title, summary, adventure count.
- Run list must return, per run: campaign title and summary (or an id the client resolves via the catalogue),
  status, created date, adventures total and adventures completed.
- Run overview must return the campaign summary, players with ready flag and character name, and adventures
  with title, intro excerpt and per-run status.
- A run whose content is missing renders per D7.

## Agent's call (listed for veto)

- How fonts and icons are sourced (the design system loads Google Fonts and Lucide from CDNs; the repo forbids
  an icon package in `structure.test.ts`).
- How the design tokens are applied — the system ships an MUI theme, and the frontend already uses MUI.
- Runs in status "finished" (not reachable yet) appear under "Archived".
