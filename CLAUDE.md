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
- Phase 7: own MCP tools `get_pending_listing` and `save_assessment`
  (`app/mcp_tools/server.py`, stdio), Listing evaluated event, `assessments`
  read model shown to moderators in F4/F5, agent service account
  (`scripts/create_agent_user.py`).

In progress / next:
- F7 AI agent (Deep Agents + Chroma RAG + Tavily MCP + our two MCP tools),
  then F8 moderator decision. Plan each with the grilling skill first.
- Gap from F4: the moderator's event history of a listing is not shown yet.
- Before running F7 on Neon: `python scripts/create_agent_user.py` once.

Decisions:
- Database: Neon PostgreSQL (cloud); tests use temporary SQLite.
- Vector DB: Chroma in `data/chroma/` (not committed).
- Embeddings: `bge-m3` via Ollama, same model for indexing and search.
- Agent LLM: `qwen2.5:3b` via Ollama (Mac with 8 GB RAM).
- Call Ollama through its HTTP API; the `ollama` Python package hangs.
- A seller's table shows their own listings plus others' Approved ones.
- MCP: official `mcp` SDK 1.x (`FastMCP`); `langchain-mcp-adapters` needs `mcp<2`.
- If web search or the model fails, nothing is saved; the listing stays Pending.
- The program, not the LLM, adds up the score and sets recommendation and confidence.
