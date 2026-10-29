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
- F7 AI agent: `python -m agent` (`agent/`), Deep Agent per listing, Chroma RAG,
  Tavily MCP, our two MCP tools; automated tests with a fake LLM and fake Tavily;
  manual tests T-AGENT-1..8 passed with the real model and Tavily (2026-10-28).
- F8 moderator decision: approve/reject on the details page (`app/commands/decide_listing.py`),
  Listing approved/rejected events, approved listings indexed in Chroma (best effort,
  catch-up `scripts/index_approved_listings.py`), moderator-only event history (F4 gap).
- All tests in `docs/tests.md` ticked (2026-10-29): pytest 196 passed, browser checks
  F1 and T-ROLE-4/5 passed, final checklist complete.

In progress / next:
- Rehearse the oral demo (`docs/tests.md` §7); activate `.venv` in both terminals.
- Before running F7 on a database: `python scripts/create_agent_user.py` and
  `python scripts/upgrade_assessments_table.py` once; on a machine:
  `python scripts/create_agent_model.py` once.

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
- Agent LLM via Ollama's OpenAI-compatible `/v1` (`langchain-openai`, no proxy),
  derived model `qwen2.5:3b-agent` (num_ctx 8192, temperature 0).
- Agent guards are in code: no save without a successful RAG and web search;
  the program fills listing_id and similar ids (RAG, similarity >= 0.55);
- If the model stops without saving while it still could, the program reminds it once.
- Fix K: the model writes no text and never sees the listing price. It reports
  `web_prices` and `description_matches_title`. The program keeps web
  prices found in the Tavily text, median = new price (<=80% of it: 50, <=100%: 25, above: 0), scores all three
  criteria (quality 25/15/5 from word count + model answer) and writes every Hebrew text (`app/pricing.py`,
  `app/listing_quality.py`). Search needs half of the title's words; similar listings same category only.
  Answers limited to 1000 tokens via `num_predict` in the derived model (Ollama
  ignores `max_completion_tokens`): rerun `scripts/create_agent_model.py`.
  Neon: run `python scripts/upgrade_assessments_table.py` once.
- Prompt never gives concrete examples (the 3B model copied them).
- F8: decision final, only from Evaluated, row locked; reject reason 5-1000 chars;
  JS confirm; no CSRF protection (user's choice, noted in Architecture §10).
- Deep Agents file tools, sub-agents and `write_todos` are hidden.
