# Demo data

Three ways to populate a catalogue: seed (ingests for real), snapshot
(restores a prepared corpus), suggestions (bulk backlog import).

> **The `backend/resources/` directory does not exist in this repository** and
> is not tracked in git — it was not carried over from the Stage-01 copy. That
> breaks the default paths of `app snapshot load` and `app suggestions import`,
> and the README's snapshot-first quick start. Either restore the directory or
> seed from scratch.

## Seed — real ingestion

```bash
docker compose exec app-web app seed demo [--auto-approve]
```

Reads 12 curated names from `backend/app/cli/data/seed_models.json` (Kawasaki
Z400, KTM 390 Duke, Yamaha YZF-R3, Honda CBR500R, Suzuki SV650, Kawasaki Z900,
Triumph Street Triple 765, Honda CB650R, BMW R 1250 GS, Honda Africa Twin,
Kawasaki Versys 650, Yamaha Tracer 9). Per model: skip if a row already exists →
create backlog → start ingestion → poll the operation (5 s interval, 600 s
timeout) → optionally approve.

Report-and-continue; it exits 1 only if **every** attempted model failed.
Output lines are `skipped (exists: …)`, `ingesting (operation …)`, `seeded`,
`approved`, `failed (…)`, then a summary.

Costs real LLM and search calls, and takes minutes per model.

**`--auto-approve` can legitimately report `failed`**: approval requires a
complete identity (manufacturer, model name, year-from), and extraction does not
always produce a year range. Fill the gap through the review form or
`app catalogue set-identity`, then approve.

## Snapshot — restore a prepared corpus

```bash
make snapshot-save ARGS=--force      # or: app snapshot save [--dir] [--force]
make snapshot-load ARGS=--replace    # or: app snapshot load [--dir] [--replace]
```

Default directory `backend/resources/catalogue-snapshot`: a `manifest.json`
(`SNAPSHOT_VERSION = 1`), `tables/<table>.jsonl.gz`, and the `DATA_DIR` /
`MEDIA_DIR` payload files. It covers the catalogue tables **only** — never
`users`, `sessions`, `chats`, `chat_messages`, `chat_preferences` or
`operations` — so restoring a corpus cannot clobber accounts or conversations.

`make snapshot-save` runs as the host uid so the written files stay editable.

## Suggestions — bulk backlog import

```bash
docker compose exec app-web app suggestions import [PATH] [--dry-run]
```

Default `backend/resources/bike-list.txt`, one proposed model per line. The
parser lifts year ranges, `[type/codes]` and footnote links into
`motorbikes.suggestion` as an **unverified claim** — research input and an
admin-visible comparison, never catalogue data. See
[`model-naming.md`](model-naming.md).

## Demo prices caveat

Any `msrp_eur` / `price_band` values that arrived by hand-seeding rather than
extraction are **plausible guesses, not verified market data**, and must never
be presented as researched figures. Real used-price research is
[not implemented](used-prices.md).

## Scripted consultation

```bash
docker compose exec app-web python scripts/demo_conversation.py
```

Eight turns over HTTP with a throwaway account, six PASS/FAIL assertions,
self-cleaning. Details in
[`chat-consultation.md`](chat-consultation.md#demo-script).
