---
author: intake
owner: human
created: 2026-09-15
updated: 2026-09-15
stage: approved
---
# Decisions

One line each. `→ file` links an attachment in `decisions/`.

- D1: The AGENTS.md rule becomes "LLM access goes through OpenRouter" — never straight to a vendor API. Image generation stays in scope as a direct call to OpenRouter's `/api/v1/images` inside the same seam, since no LangChain binding exists for it.
- D2: One generic failure line plus a retry affordance for every failure class; the provider's exact message, where one is present, sits behind a "more" disclosure.
- D3: The seam carries both token counts and USD cost from day one; which of the two the player sees is decided in the play-screen phase.
- D4: Portraits use the better of the two image models our OpenRouter account serves — Gemini 3.1 Flash Image, pinned as `IMAGE_MODEL=google/gemini-3.1-flash-image` in `.env.dist`.
- D5: A run pins the prompt version it starts with, the way it pins the content version; editing a prompt on disk never changes a playthrough already in flight.
- D6: The seam retries the retryable failure classes quietly with backoff before the player sees anything; only once those are exhausted does D2's message appear.
