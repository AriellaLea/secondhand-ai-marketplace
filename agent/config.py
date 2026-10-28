"""Settings of the agent process. Secrets (Tavily key, database URL) come from .env.local only."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env.local")

# LLM: a derived Ollama model (scripts/create_agent_model.py), called through
# Ollama's OpenAI-compatible HTTP endpoint, not the `ollama` package (it hangs).
AGENT_BASE_MODEL = "qwen2.5:3b"
AGENT_MODEL = os.getenv("AGENT_MODEL", "qwen2.5:3b-agent")
AGENT_NUM_CTX = 8192
# Longest model answer: plenty for a tool call; a 3B model once rambled for 10 minutes.
AGENT_MAX_TOKENS = 1000

POLL_SECONDS = 10
# One listing takes about 4 minutes on a Mac with 8 GB of RAM.
LISTING_TIMEOUT_SECONDS = 600
# Each tool call takes about two graph steps; this leaves room for a few retries.
RECURSION_LIMIT = 30
# A failed listing is skipped for this long, then tried again.
RETRY_AFTER_SECONDS = 300

# RAG: bge-m3 scores real matches at about 0.58-0.69 and unrelated items below 0.55
# (measured with scripts/try_similar.py on the sample listings).
SIMILAR_K = 5
SIMILARITY_MIN = 0.55
# A 3B model often stops after a refusal: if it stops without saving while it still
# could, the program reminds it this many times.
SAVE_REMINDERS = 1

# Web search through the Tavily MCP server, version pinned.
TAVILY_MCP_PACKAGE = "tavily-mcp@0.2.22"
TAVILY_MAX_SEARCHES = 2
TAVILY_MAX_RESULTS = 5
TAVILY_OUTPUT_MAX_CHARS = 3000
# A search query must contain a word of the listing title at least this long.
QUERY_WORD_MIN_LETTERS = 2

LOG_FILE = ROOT / "logs" / "agent.log"
