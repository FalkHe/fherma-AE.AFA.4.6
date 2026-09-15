---
author: intake
owner: human
created: 2026-09-15
stage: approved
---
# Sprint 04: an embedding call round-trips and reports what it cost

## Outcome
`app llm embed "<text>"` returns a vector of `EMBEDDING_DIMENSIONS` values
together with that call's token count and USD cost.

## Acceptance criteria
- AC1: with a real key, the command prints the vector's length, and it equals `EMBEDDING_DIMENSIONS` (1536).
- AC2: the same run prints the call's token count and USD cost.
- AC3: several texts passed in one invocation return one vector each, in the order given.
- AC4: the gateway failures of sprint 02 raise the same eight codes here — asserted without a key.
- AC5: no `dimensions` parameter is ever sent; the model's native width is what `EMBEDDING_DIMENSIONS` must match.

## Decisions
← D1, D3

## Assumptions
- The call goes to OpenRouter's `/api/v1/embeddings` directly rather than through `OpenAIEmbeddings(base_url=…)`, because LangChain drops the non-standard `usage.cost` field D3 requires.
- The seam's signature is `embed_texts(texts) -> vectors + usage`, a module function like the rest.

## Out of scope
pgvector, any embedding column, any storage or similarity search at all — that
is phases 4 and 6. This sprint ends at the returned vector.
