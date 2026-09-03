# Demo walkthrough

Two demo assets exist. Pick whichever fits:

- **`backend/scripts/demo_conversation.py`** — a scripted, self-cleaning demo
  over the real HTTP API. It registers a throwaway account, drives an
  eight-turn interview and asserts the phase's grading-relevant behaviour
  (≥3 distinct tool calls, sources on retrieved knowledge, recommendations
  pointing at approved models, exactly one backlog row for an uncatalogued
  bike, resumability). Run it with:

  ```bash
  docker compose exec app-web python scripts/demo_conversation.py
  ```

  Read the script's own module docstring for what it asserts and why. It
  deletes everything it created when it finishes (or fails), so there is
  nothing left afterwards to click through in a browser.

- **This document** — a browser-replayable walkthrough for a human grader:
  sign in, have a short consultation, browse the catalogue the advisor draws
  its recommendations from (including the out-of-chat sources/provenance
  surface), then — in the submission chapter (§6) — build the whole story
  from an empty database: register, promote an admin, ingest a model,
  approve it live, and use the resulting catalogue in a consultation. Every
  URL, curl command and expected outcome below was replayed against a
  fresh clone with an empty database at `HEAD 51eb323` on 2026-08-29
  (step 5.18's acceptance run). Each numbered item below
  names the `docs/core-requirements-checklist.md` row it demonstrates, in brackets.

## Prerequisites

- Stack up: `make up` (or `docker compose up -d`).
- Frontend: <http://localhost:5173>, backend API: <http://localhost:8000>.
- **This walkthrough is deliberately count-agnostic.** The catalogue's exact
  contents depend on what has been seeded/ingested and approved — nothing
  below assumes a fixed number of models or a specific id. Chapters 1–5
  assume *some* approved catalogue already exists (seed it first, see below,
  or replay §6 which builds one from an empty database as part of the
  walkthrough itself). Wherever a chapter needs "a model", pick any approved
  one; wherever it needs "a filter that narrows the grid", pick any
  attribute your current catalogue actually varies on (category is usually
  the most reliable).
- The quickest way to get a catalogue to demonstrate against is to restore
  the committed one: `make snapshot-load` (see README's "Restoring the demo
  catalogue from the snapshot"). It needs no API keys and no network, and it
  brings the embeddings with it, so retrieval and every tool call work
  immediately.
- To *ingest* a catalogue quickly instead of building one by hand (§6 does
  the by-hand version): `docker compose exec app-web app seed demo
  --auto-approve` (see README's "Seeding the demo catalogue"). This is a
  *bulk convenience* — it does not replace live-reviewing one model, which
  §6 still walks through explicitly.

## 1. Sign in as a plain user

Open <http://localhost:5173/register> and register a throwaway account:

- Username: 3–32 chars, lowercase letters/digits/`_`/`.`/`-` only (e.g.
  `demo-catalogue`).
- Password / confirm password: 8+ chars, identical.

Submitting redirects straight into the app at `/consultations` (the
`RegisterRoute` chains a login call after registration — the backend's own
`POST /auth/register` does not set a session cookie by itself, on purpose:
there is exactly one place cookies are issued, `POST /auth/login`).
`[technical implementation → user input validation]`

## 2. A short consultation → a recommendation card

Click **"Ask the advisor"** (or go directly to `/consultations` and start a
new one). The advisor greets first. Send turns one at a time, waiting for
each reply before sending the next (the composer disables itself while a
reply is in flight):

1. `Hi! I passed my A2 test last month and this would be my first own bike.`
2. `I ride to work almost every day, about 20 km each way through city traffic, plus the occasional Sunday tour.`
3. `I am 1.72 m tall with an inside leg of roughly 80 cm, and I would like to stay around a few thousand euro.`
4. `Alright — please show me your shortlist, even if it is only one or two bikes, and tell me how they're actually regarded by riders.`

**The advisor is a live, non-deterministic LLM.** Wording varies every run,
tool-call sequencing varies, and occasionally a turn needs a repeat or a
follow-up nudge before a recommendation card appears (`demo_conversation.py`
retries once for the same reason) — e.g. if the catalogue's A2-eligibility
data is noisy for the models you seeded, the advisor may report zero A2
matches and ask whether to widen the search (categories, or drop the strict
power limit) before it can recommend anything; answering that follow-up
reaches a card. This is the expected behaviour of an autonomous tool-calling
loop, not a defect. `[≥3 tools, RAG, personalisation]`

Leave this consultation open — chapter 4 below returns to its recommendation
card.

## 3. Catalogue chapter

### 3.1 Open the catalogue

Click **Catalogue** in the top nav (between Consultations and Admin), or go
directly to <http://localhost:5173/catalogue>. Every approved model renders
as a card; nothing else in the database is visible here (backlog/in-review/
rejected rows are excluded server-side, for every role). `[UI: shows context]`

### 3.2 Apply a filter combination that visibly narrows

In the filter panel (sidebar on desktop, **Filters** button drawer below the
`md` breakpoint), set **Category** to any value your catalogue has more than
one of (e.g. **Naked**), then add an engine-displacement or seat-height bound
that further narrows the grid. There is no Apply button: the selects, sliders
and the A2 checkbox apply the moment you change them, and the typed numeric
bounds (max seat height, max weight) apply when the field loses focus or you
press Enter — so tab away after typing. The result count drops below the
unfiltered total; which models remain depends on your catalogue's contents,
not a fixed pair of names.

### 3.3 Copy/reload the URL

The address bar reflects the filter state, e.g.:

```
http://localhost:5173/catalogue?category=naked&ccMin=400&ccMax=700
```

Copy that URL, open it in a fresh tab (or reload the page). The filter
controls reappear pre-filled and the grid still shows the same narrowed set
— the URL is the only state. Signing out first and pasting the URL into the
login flow also works: `main` preserves the query string through the
redirect (`RequireAuth` passes the full `location`, including `search`, and
`LoginRoute` reads `from.pathname + from.search`).

### 3.4 Open a model detail page

Click any card. The page shows, top to bottom:

- **Verified specs** — a grouped table (Engine & performance, Dimensions &
  ergonomics, Licence & safety, Classification & price) of the frozen spec
  fields; null fields render no row at all (never a dash on this surface).
- **About this bike** — the Wikipedia article's markdown prose (headings,
  tables, references) — the *only* prose customers see; scraped
  product/magazine pages never render wholesale here.
- **Sources** — a permanently expanded panel (never a collapsible toggle)
  listing every retrieved document's title + external link. This is the
  out-of-chat provenance surface — it exists independently of any chat
  conversation. `[RAG, UI: shows sources]`
- **Image + attribution** — the approved photo with its licence attribution
  string rendered visibly beneath it.

### 3.5 Sort by price

Back on `/catalogue`, clear the filters and set **Sort by → Price (low to
high)** (URL gains `&sort=price`, mapped server-side to `msrpEur` ascending,
NULLS LAST). Models with an extracted price sort ahead of those without one;
today's approved models get their `msrpEur`/`priceBand` from real pipeline
extraction, not a hand-entered guess — some fields are simply `null` when
extraction found nothing to cite.

### 3.6 A non-approved id 404s

Open <http://localhost:5173/admin> as an admin (§6.2 shows how to get one)
and copy a backlog/in-review row's id from the URL, or use any
syntactically-valid-but-nonexistent 26-character ULID. Visiting
`http://localhost:5173/catalogue/<that id>` shows the "Model not found" empty
state, not a leaked draft — unknown and non-approved ids are
indistinguishable, by design. `[technical implementation → error handling]`

## 4. Recommendation-card click-through

Return to the consultation opened in chapter 2 (`/consultations` → the
chat). Click a recommendation card. It navigates to that model's catalogue
detail page — the identical page from §3.4, specs/article/sources/
attribution and all. The whole card surface is a real link (`Ctrl`/`Cmd`-click
or middle-click opens it in a new tab too). `[UI: displays tool call results]`

## 5. Role-scoping curl replay

Graders who want to prove the security story without the UI can replay this
directly against the API. Each snippet is self-contained (uses a cookie jar
file for the session); `-g` on the JSON:API query calls is required — without
it curl reads the `[...]` in `page[size]`/`filter[category]` as a glob range
and refuses the URL (`curl: (3) bad range in URL`):

```bash
# 1. Register a throwaway account and sign in (cookie jar captures the session).
curl -s -c cookies.txt -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"demo-curl","password":"a-long-enough-password"}'
# -> 201, {"id":"...","username":"demo-curl","role":"user"}

curl -s -c cookies.txt -b cookies.txt -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo-curl","password":"a-long-enough-password","rememberMe":false}'
# -> 200, {"id":"...","username":"demo-curl","role":"user"}

# 2. A plain user CAN read the customer catalogue resource.
curl -s -g -b cookies.txt "http://localhost:8000/api/catalogue-models?page[size]=100" \
  -o /dev/null -w '%{http_code}\n'
# -> 200

# 3. A plain user CANNOT read the admin-only products resource
#    (the Phase-2 pin: all admin endpoints stay admin-only, reads included).
curl -s -b cookies.txt http://localhost:8000/api/products -o /dev/null -w '%{http_code}\n'
# -> 403 {"detail":"Admin privileges required."}

# 4. Pick any approved model id from step 2's response, then confirm a
#    syntactically valid but nonexistent id 404s on the customer detail
#    endpoint (no existence leak between "unknown" and "exists but not
#    approved" — swap the trailing character to get a nonexistent id from a
#    real one).
curl -s -b cookies.txt http://localhost:8000/api/catalogue-models/01ZZZZZZZZZZZZZZZZZZZZZZZZ \
  -o /dev/null -w '%{http_code}\n'
# -> 404

# 5. The filter combination from §3.2, over the wire (JSON:API filter names).
curl -s -g -b cookies.txt \
  "http://localhost:8000/api/catalogue-models?filter[category]=naked"
# -> 200, meta.totalCount reflects however many naked models are approved
```

Registering repeatedly with the same username 409s on step 1 — change the
username, or delete the throwaway row afterwards to leave the database
exactly as found:

```bash
docker compose exec postgres psql -U app -d application \
  -c "DELETE FROM users WHERE username = 'demo-curl';"
```

(`ON DELETE CASCADE` removes the account's chats/messages/preferences with
it.) `demo_conversation.py` does the equivalent cleanup automatically for
its own throwaway account.

## 6. Submission chapter: the whole story from an empty database

This chapter replays the full grading story end to end, starting from a
database with **no users and no models** (a fresh clone after `make up` +
first-run setup is exactly this state). It is the walkthrough a grader
following the README from scratch would naturally produce. Every step below
was live-replayed against a fresh clone at `HEAD 51eb323` on 2026-08-29.

### 6.1 Register, then become the first admin

Register through the UI (`/register`, same rules as §1) or via curl (§5 step
1). No HTTP endpoint grants the admin role — promote the account from the
CLI, per the README's "Creating the first admin":

```bash
docker compose exec app-web app users set-role <your-username> admin
```

Re-running it is a no-op. **Promotion keeps the account's existing sessions
alive** — live sessions read the role fresh, so the Admin nav appears on the
next page load without signing out. Only a *demotion* (`... set-role <name>
user`) or a password reset revokes that account's sessions.
`[domain specialisation → security]`

### 6.2 Add a model to the backlog and watch ingestion progress

Open <http://localhost:5173/admin> and add a model by name that is **not**
already in your catalogue in any status (the admin UI reports a
`duplicate-model` error otherwise). Watch the row move `backlog` →
`ingesting`, with live progress over the SSE connection
(`GET /api/events`, `operation.updated` notifications feeding
`OperationProgress`) — no polling, no page refresh needed.
`[real-time KB updates, UI: progress indicators]`

Equivalently from the CLI (same pipeline, no bypass — `docs/ingestion.md`):

```bash
docker compose exec app-web app ingest run "<Manufacturer Model>"
```

Ingestion runs Wikipedia lookup → web search (if `TAVILY_API_KEY`/
`SEARCH_PROVIDER` is configured) → fetch and store each document → download
an image → LLM spec extraction into a draft → chunk and embed the stored
documents, landing the entry in `in_review`. In this replay it completed in
well under a minute; timing varies with how many sources are found and how
responsive the upstream sites are.

### 6.3 Live admin review + approve (the admin-verified story)

Open the model's review screen (`/admin/models/:motorbikeId`). Check the
fetched documents, the editable draft specification (plus the "Additional
extracted data" table of everything the extractor found beyond the fixed
fields), and the downloaded image with its licence attribution. Click
**Approve & publish** and confirm in the "Publish this model?" dialog — this
promotes the draft specification to verified and the image to approved,
moving the entry to `approved` (published to the customer catalogue
immediately, no restart — `[real-time KB updates]`). This
one live, human-in-the-loop review is what earns the "admin-verified"
claim — nothing in this repo publishes a model to customers without it.

### 6.4 The bulk-seed shortcut (for context, not a replacement)

`app seed demo [--auto-approve]` drives the same create → ingest → transition
sequence as §6.2–6.3, but scripted across the curated 12-model list in
`backend/app/cli/data/seed_models.json`, and `--auto-approve` calls the same
review-transition service an admin's approval click uses instead of a human
clicking it. This is a **bulk convenience for bootstrapping a demo
catalogue quickly** — it does not replace the live review in §6.3, and a
grader should still expect to find one model that was reviewed and approved
by hand if the whole submission chapter was followed.

### 6.4b Restoring instead of ingesting (for context, not a replacement)

`make snapshot-load` restores the committed catalogue — rows, documents,
images and embeddings — without ingesting anything. It is how a grader gets a
populated instance in seconds and at zero API cost, and how §1–5 can be
replayed without waiting on a pipeline run. It is explicitly **not** part of
the grading story for ingestion or review: nothing about a restore
demonstrates that the pipeline works, which is why §6.2–6.3 build one model
live, by hand, from an empty database.

### 6.5 A consultation with real tool calls, sources and recommendations

Start a new consultation (§2's flow) against the catalogue you just grew.
Interview turns that establish a licence class, a use case, a height/budget,
and then ask for a shortlist "including how they're actually regarded by
riders" reliably drive the advisor through several distinct tool calls in one
turn — a live replay of this chapter used five:
`catalogue_search` → `record_preference` (× several, one per captured
preference) → `retrieve_bike_knowledge` → `licence_fit_check` →
`present_recommendations`. Check, in the chat UI:

- **Tool call results** — each tool call renders its own block under the
  assistant's reply (`ToolResultBlock`). `[UI: displays tool call results]`
- **Sources** — the reply that cites retrieved knowledge shows a sources
  list (`MessageSources`), each entry a real document title + URL.
  `[RAG, UI: shows sources]`
- **Recommendation cards** — one per recommended model, each with an image,
  a rationale, matched preferences and key specs.

### 6.6 Card click-through → filtered catalogue URL → reload

Click a recommendation card (§4's mechanism) to land on that model's
catalogue detail page. From there, go to `/catalogue`, apply a filter that
matches the recommended model's category (§3.2), copy the resulting URL, and
reload it in a fresh tab or after signing out and back in (§3.3) — the same
filtered grid reappears from the URL alone.

### 6.7 Logout / login resume

Log out (top-right menu). Log back in with the same account. `/consultations`
still lists the consultation from §6.5 with its full history — resumability
is persistence (every message and captured preference lives in PostgreSQL;
reopening a chat rebuilds the LLM context from history, per
`docs/architecture.md`'s LLM/Agent Architecture section), not a client-side
cache.

## Notes for a fresh reader

- This walkthrough makes no assumption about how many models are approved or
  what their ids are — every chapter picks "any approved model" or "a filter
  your catalogue actually varies on" rather than naming one. A different
  dev/CI database narrows to different counts at the same filter values —
  the *mechanism* (filter narrows the grid, URL round-trips, detail page
  renders specs/prose/sources/attribution, cards link through, tool calls
  and sources render, ingestion is admin-triggered and live-progressed) is
  what's being demonstrated, not the exact numbers.
- Chapter 2 and 6.5's turn wording is illustrative, not exact-match
  required — any phrasing that establishes a licence class, a use case and a
  budget/height, then asks for a shortlist, reaches a recommendation (or a
  graceful "no exact match, widen the search?" follow-up, itself a valid
  demonstration of the tool-calling loop's error handling).
- Prices shown in the catalogue (chapters 3.4, 3.5) are real pipeline
  extraction output where the source material stated one, and `null` where
  it didn't — there is no hand-entered guess left in this catalogue's price
  data (the earlier Phase-4 demo fixtures that carried guessed prices have
  since been removed from the database entirely).
- See `docs/core-requirements-checklist.md` for the full requirement-to-file mapping this
  walkthrough exercises; the `[bracketed]` tags above point at its rows.
