# Project vision

## What this is

A conversational AI advisor that helps a person choose a motorcycle. It
interviews them about their needs, then recommends models grounded in **both**
verified specifications and retrieved prose about how those bikes are actually
regarded.

## Why it exists

A buyer researching a motorcycle gets three bad options: manufacturer marketing,
forum folklore, or an LLM's training data — outdated, unattributable, and
confidently wrong about numbers. This project's answer is a **curated internal
database**: every specification is extracted from fetched sources and then
*approved by a human* before a customer can see it, and every prose claim the
advisor makes is retrieved from a stored document with visible provenance.

That single decision drives most of the architecture:

- **Specs are LLM-extracted, admin-verified.** Extraction produces a *draft*;
  approval promotes it to *verified*. Only approved models are visible to
  customers, and only verified specs answer a spec question.
- **Sources are retained permanently.** We fetch every page ourselves rather
  than trusting a search API's copy, so provenance and raw bytes survive.
- **The advisor may not judge a bike from memory.** A named model is looked up
  through a tool; numbers come from the catalogue, opinion comes from retrieved
  chunks.

## The product

- **Consultation is a guided interview.** The advisor opens the conversation
  (like a seller in a store), works through experience → licence → use case →
  budget → physique → preferences, and records each answer with a *firmness*
  (`hard` constraint / `soft` leaning / `exploring`). It steers; free-form
  questions are still allowed.
- **Recommendations render as cards in the chat**, linking to model detail
  pages. There is no separate comparison screen — comparison happens
  conversationally through a tool whose result renders inline.
- **Retrieved sources and tool results are visible in the UI**, alongside
  progress indicators for the long operations.
- **Everything is behind a login.** Open self-signup; roles `user` and `admin`;
  admin granted via CLI.
- **Admins own the catalogue.** A model enters the backlog either because an
  admin added it or because the advisor flagged a bike a customer mentioned that
  isn't catalogued yet. Ingestion, review and approval happen in the admin UI;
  the CLI only bootstraps the first admin and provides the building blocks.

## Domain constraints worth knowing

Motorcycle identity is genuinely harder than "name + year": the same marketing
name can span several technically incompatible generations, and displacement in
a name rarely matches actual displacement. How that is modelled — and where the
implementation deliberately simplifies the domain — is
[`../modules/model-naming.md`](../modules/model-naming.md).

## Course context

Turing College project. This repository is **AE.AFA.4.6 (Sprint 4, "Stage
02")** and started as a copy of **AE.AFA.3.5 (Sprint 3, "Stage 01")**. The
briefs are `/125.md` (Stage 01 — domain-specialised RAG chatbot) and `/135.md`
(Stage 02 — AI agent project). Stage 01's graded requirements are all
implemented and remain binding:

| Requirement | Implementation |
|---|---|
| LLM access via **OpenRouter**, integrated through **LangChain** — never the OpenAI API directly | `llm/models.py` (`ChatOpenRouter`), `llm/embeddings.py` |
| **Advanced RAG**: query translation + structured retrieval, deliberate chunking, embeddings | [`../modules/retrieval-advisor.md`](../modules/retrieval-advisor.md), [`ingestion.md`](../modules/ingestion.md) |
| **≥ 3 tool calls** relevant to the domain | eight registered tools |
| **React UI** showing retrieved context/sources, tool results, progress | [`../modules/chat-consultation.md`](../modules/chat-consultation.md), [`../modules/catalogue.md`](../modules/catalogue.md) |
| Error handling, input validation, domain-appropriate security | [`security.md`](security.md) |

Bonus tasks claimed by design: hybrid search (hard); user authentication and
personalisation, prompt-injection protection, logging/monitoring via Langfuse,
and real-time knowledge-base updates through admin-triggered ingestion
(medium). The Langfuse claim is narrow — see
[`observability.md`](observability.md).
