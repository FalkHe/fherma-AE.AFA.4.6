---
author: Falk Hermann <307901131+falkhetc@users.noreply.github.com>
owner: human
created: 2026-09-19
updated: 2026-09-22
stage: approved
---
# Decisions

One line each. `→ file` links an attachment in `decisions/`.

- D1: Scope is option B: the backend gains read-only additions — a campaign catalogue and a campaign-run overview
  (players with a ready flag, adventures with status) — and the frontend is built on top. The Start button exists but
  stays disabled; wiring it up belongs to the adventure-entry intent.
- D2: The dashboard shows one list of every campaign run I am a member of. No separate "participated" section
  until sharing exists; splitting the list comes with that feature.
- D3: The dashboard offers the tags "In progress", "New" and "Archived"; archived runs are visible under their tag,
  muted and view-only (no unarchive). (rev 2026-09-19, was: every non-archived run in one list, archived hidden)
- D4: "Create character" looks active; clicking it opens the "in development" dialog (D13). The real flow arrives in
  the next intent. (rev 2026-09-19, was: shown but disabled, with a hint that creation is not available yet)
- D5: An anonymous visitor opening any protected page is redirected to sign-in, with sign-up one click away. After
  signing in they return to the page they originally asked for.
- D6: A player may start any number of runs of the same campaign. The select dialog neither warns nor blocks.
- D7: A run whose campaign content no longer exists stays on the dashboard, labelled as an unavailable campaign in a
  muted style. It cannot be opened; clicking only explains why.
- D8: A player with no runs sees a short invitation to start their first campaign together with the same
  prominent "New Campaign" button.
- D9: Adventures are listed in campaign order. The first unplayed one reads "Next up" when every character is ready,
  otherwise "Waiting on party" with a hint why; it carries the "Start adventure" button. Later ones read "Locked",
  finished ones "Done". (rev 2026-09-19, was: Next / Locked / Done)
- D10: Choosing a campaign in the select dialog creates the run and opens its run screen directly.
- D11: Dashboard and run screen follow the delivered design → decisions/D11-dashboard-design.md. A run card shows a
  cover-art placeholder, campaign title, status badge, campaign summary, an "Adventure n of m · 1 player · Created …"
  line and a "Begin" (new) or "Resume" (in progress) button.
- D12: The dashboard opens on "In progress"; when nothing is in progress it opens on "New". With no runs at all the
  invitation of D8 shows instead.
- D13: One "in development" dialog is used for features that exist in the design but not yet in the product; its
  message is along the lines of "Be brave, this feature is in development." The "Invite a player" tile stays on the
  run screen and opens it.
- D14: The product is called "The Goblin's Tavern" in the header, and the delivered dark-only design system is
  adopted throughout.
