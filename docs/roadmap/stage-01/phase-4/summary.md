# Phase 4 — Customer catalogue

**Goal:** Give signed-in customers a browsable, filterable, shareable motorcycle catalogue that recommendation cards can link into.

## Delivered

- **Customer catalogue API** — a new read-only `/api/catalogue-models` resource: a slim filtered/sorted list (11 card attributes) and a self-contained detail payload (13 verified specs, article prose, sources, images), serving approved models only for every role.
- **Filtering and sorting** — nine filter families (manufacturer, category, price band, engine/power ranges, seat height, weight, A2 eligibility) reusing the advisor's existing filter vocabulary and SQL clause builder; sort by name or price with priceless models always last.
- **Catalogue list page** (`/catalogue`) — responsive card grid, filter panel, server-driven pagination, and a new main-nav entry; the URL is the single source of filter state, so a filtered view survives reload and can be shared.
- **Model detail page** (`/catalogue/:motorbikeId`) — image gallery with attribution, the 13 verified specs grouped into four sections (empty fields and empty groups hidden), Wikipedia article prose, and an always-expanded Sources block — the provenance surface required for grading, outside the chat.
- **Recommendation cards now click through** — Phase-3 cards became links to the matching detail page, closing the contract Phase 3 reserved.
- **Manufacturer list opened to signed-in users** (was admin-only), so the manufacturer filter can be populated.
- **Live updates** — admin-approving a model refreshes open catalogue views via the existing server-event channel.
- **Demo walkthrough** (`docs/demo-walkthrough.md`, since removed) — a replayable browse → filter → share → detail → card click-through chapter, plus curl commands proving role scoping for graders.
- **Acceptance evidence run** — fresh-user browser walk, independent role-scoping/filter matrix, and a 360 px mobile pass; tagged `phase-4-done`.

## Non-obvious decisions

- **A separate customer resource instead of opening the admin `/api/products`** — keeps the admin contract, tests and UI untouched and makes it structurally impossible for customers to see unapproved data or draft specs.
- **Only Wikipedia prose is shown in full; scraped product/magazine pages appear as links only** — serving marketing copy wholesale would contradict the product's "not marketing-biased" premise, while the link list still satisfies the source-display requirement.
- **Unapproved and unknown models both answer a plain 404** — deliberately indistinguishable, so the catalogue cannot be used to discover unreleased pipeline entries.
- **Browsing includes models with no verified specs; any stated spec filter excludes them** — the opposite rule from the advisor's candidate search, chosen so an empty catalogue does not look broken. The two queries were deliberately not unified.
- **Two frontend pages built entirely on stub data before the API existed**, then switched over in one step — let the frontend and backend tracks run in parallel with a single sync point.
- **URLs carry short, SPA-friendly parameter names, translated to wire names in one place** — shareable links stay readable without coupling them to the API vocabulary. Model identity in URLs is the internal ULID, trading pretty URLs for one identity scheme.
- **Zero migrations, zero new dependencies, zero new config keys** were imposed as phase-wide constraints; every need was met by composing existing reads.
- **Demo prices are owner-approved guesses, not researched market data** — needed to make price sorting and price bands demoable; flagged as unverified in the docs.

## Not delivered / deferred

- **Concurrent-turn race fix (step 4.5) — dropped.** The planned migration-free row lock was proven insufficient (the check and the claim sit in different transactions, so no lock can serialize them). Any real fix relaxes a Phase-3 design pin, which is an owner decision; the issue stays open (Phase-4 `open-questions.md` OQ4) and is not reachable through the UI.
- **Researched real MSRP prices** — deferred past Phase 4, to be entered through the existing admin review flow.
- **Customer-facing endpoints for documents and images** — none created; both are reachable only through the model detail payload.
- **Post-login redirect dropping the query string** — found during the wiring step, fixed in-phase during the docs step.
- **Non-blocking polish from the acceptance run** — routed to Phase 5 (hardening & submission).
