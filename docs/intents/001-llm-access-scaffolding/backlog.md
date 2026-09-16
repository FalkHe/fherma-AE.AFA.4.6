---
author: intake
owner: human
created: 2026-09-15
updated: 2026-09-15
stage: approved
---
# Backlog

Sprint outcomes, dependency-ordered. Status: `open | running | done`.

| # | Outcome (one verifiable statement) | Depends on | Issue | Status |
|---|---|---|---|---|
| 01 | `app llm chat "<prompt>"` answers from the configured OpenRouter chat model and prints that call's prompt/completion tokens and its USD cost | – | #1 | done |
| 02 | Every gateway failure the seam can meet surfaces as its own domain code behind one generic failure line, the provider's own wording only under `--details` | 01 | #2 | done |
| 03 | A retryable failure is retried with backoff — each attempt visible in the log — and the failure line appears only once the attempts are spent | 02 | #3 | done |
| 04 | `app llm embed "<text>"` returns a vector of `EMBEDDING_DIMENSIONS` values together with that call's token count and USD cost | 02 | #4 | done |
| 05 | `app llm image "<prompt>" --out <file>` writes a portrait PNG that opens, and prints that call's USD cost | 02 | #5 | done |
| 06 | `app prompt show <capability>/<kind>/<id>` prints the text of a named prompt version; an unknown id and a malformed id fail differently | – | #6 | done |
| 07 | A value checkpointed under a `thread_id` by one CLI run is read back by the next, out of the checkpointer's own schema, which Alembic leaves untouched | – | #7 | open |

## Notes

- 01, 06 and 07 have no predecessor and may run in parallel. 01 sets the
  `langchain-*` floors, 07 the `langgraph-*` ones — whichever lands first pins them.
- The D1 amendment of AGENTS.md ("through OpenRouter", not "through LangChain")
  and the matching `docs/architecture.md` / `docs/general/backend-stack.md`
  corrections belong to 01, which is where the seam first exists.
- D4's `IMAGE_MODEL=google/gemini-3.1-flash-image` is already in `.env.dist`; 05
  consumes it and adds nothing there.
- 01, 04 and 05 are live round-trips: a human runs them by hand with a real
  `OPENROUTER_API_KEY`. 02, 03, 06 and 07 are checkable without a key (empty key,
  an override base URL, the filesystem, postgres) and are the only ones CI can assert.
- pgvector and embedding *storage* stay out of this intent (phase 4/6); 04 ends
  at the returned vector.
- Decision coverage: D1 → 01, 05 · D2 → 02 · D3 → 01, 04, 05 · D4 → 05 ·
  D5 → 06 · D6 → 03.

## Proposals

<none yet>
