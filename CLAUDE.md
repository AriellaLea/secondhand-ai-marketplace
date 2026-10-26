# CLAUDE.md

## Before coding
Always read these first:
- `docs/PRD.md`
- `docs/Architecture.md`
- `docs/tests.md`

## Rules
- Follow MVC, CQRS and Event Sourcing.
- Implement one feature at a time.
- Never read, print or modify `.env.local`.
- Never commit secrets.

## Current status
Done:
- F1 auth, F2 publish listing (event-sourced), F3 search, F4 listing details,
  F5 listings table, F6 moderator dashboard.
- Phase 6: Chroma vector DB with 30 sample listings (`app/vector_store.py`,
  `scripts/load_sample_listings.py`, `scripts/try_similar.py`).

In progress / next:
- Phase 7: two own MCP tools (get pending listing, save assessment).
- Then F7 AI agent, then F8 moderator decision.

Decisions:
- Database: Neon PostgreSQL (cloud); tests use temporary SQLite.
- Vector DB: Chroma in `data/chroma/` (not committed).
- Embeddings: `bge-m3` via Ollama, same model for indexing and search.
- Agent LLM: `qwen2.5:3b` via Ollama (Mac with 8 GB RAM).
- Call Ollama through its HTTP API; the `ollama` Python package hangs.
- A seller's table shows their own listings plus others' Approved ones.
