"""Ingestion building blocks: fetch a page, extract its text, keep the original.

The modules here are deliberately free of database and job concerns — they take
a URL or a string and return a value. `fetch` and `extract` never raise for an
expected outcome (a timeout, an oversized page, a PDF, an article with no main
text): they return a typed failure, because only the caller knows whether a
missing source is a warning on the operation or the end of the run.

The ingestion job (step 2.14) is the piece that composes them: fetch → store
raw payload → extract → `document_service.create_document`.
"""
