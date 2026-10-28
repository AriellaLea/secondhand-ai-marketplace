"""The AI agent process (F7): evaluates listings in status Pending evaluation, one at a time.

It runs on its own, separate from the Flask app, and reaches the data only through
our MCP tools (get_pending_listing, save_assessment); the web through Tavily's MCP server.

Usage:
    python scripts/create_agent_model.py   # once
    python -m agent                        # keep checking every few seconds (Ctrl+C to stop)
    python -m agent --once                 # evaluate what is pending now, then exit
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import urllib.request
from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncIterator, Callable

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agent.config import (
    AGENT_MODEL,
    LOG_FILE,
    POLL_SECONDS,
    RETRY_AFTER_SECONDS,
    ROOT,
    TAVILY_MCP_PACKAGE,
)
from agent.llm import make_llm
from agent.runner import evaluate_listing
from agent.tools import call_mcp
from app.vector_store import EMBEDDING_MODEL, OLLAMA_HOST, find_similar_listings

log = logging.getLogger("agent")

MCP_TOOL_NAMES = {"get_pending_listing", "save_assessment", "tavily_search"}


class FatalAgentError(Exception):
    """Nothing can be evaluated until a person fixes the setup."""


def setup_logging() -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(LOG_FILE, encoding="utf-8")],
        force=True,  # a library may have configured logging already
    )
    for noisy in ("httpx", "mcp", "langchain_mcp_adapters"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def startup_problems() -> list[str]:
    """What must be fixed before the agent can work (checked once at start)."""
    problems = []
    if not os.getenv("TAVILY_API_KEY"):
        problems.append("TAVILY_API_KEY is missing. Set it in .env.local.")
    if not os.getenv("DATABASE_URL"):
        problems.append("DATABASE_URL is missing. Set it in .env.local.")
    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=10) as response:
            names = {model["name"] for model in json.load(response)["models"]}
    except OSError as exc:
        return problems + [f"Cannot reach Ollama at {OLLAMA_HOST} ({exc}). Start it with: ollama serve"]
    if AGENT_MODEL not in names:
        problems.append(f"Model {AGENT_MODEL} is missing. Run: python scripts/create_agent_model.py")
    if EMBEDDING_MODEL not in names and f"{EMBEDDING_MODEL}:latest" not in names:
        problems.append(f"Model {EMBEDDING_MODEL} is missing. Run: ollama pull {EMBEDDING_MODEL}")
    return problems


@asynccontextmanager
async def open_mcp_tools() -> AsyncIterator[dict[str, BaseTool]]:
    """One session per MCP server, kept open for the whole run (starting them is slow)."""
    env = dict(os.environ)  # the servers read their secrets from it, never from the command line
    servers = [
        StdioServerParameters(command=sys.executable, args=["-m", "app.mcp_tools.server"], env=env, cwd=ROOT),
        StdioServerParameters(command="npx", args=["-y", TAVILY_MCP_PACKAGE], env=env),
    ]
    async with AsyncExitStack() as stack:
        tools = {}
        for params in servers:
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            # Tool errors raise, so the program sees them before the model does.
            for tool in await load_mcp_tools(session, handle_tool_errors=False):
                if tool.name in MCP_TOOL_NAMES:
                    tools[tool.name] = tool
        yield tools


async def run_agent(
    once: bool = False,
    open_tools: Callable = open_mcp_tools,
    make_model: Callable = make_llm,
    similar: Callable = find_similar_listings,
) -> None:
    excluded: dict[str, float] = {}  # listing id -> when it failed
    fatal = None
    unreadable = False  # the last get_pending_listing failed
    async with open_tools() as mcp_tools:
        log.info("Agent started (model %s). Waiting for listings in status Pending evaluation.", AGENT_MODEL)
        while True:
            now = time.monotonic()
            for listing_id, failed_at in list(excluded.items()):
                if now - failed_at >= RETRY_AFTER_SECONDS:
                    del excluded[listing_id]  # try it again
            try:
                _, listing = await call_mcp(mcp_tools["get_pending_listing"], {"exclude_ids": list(excluded)})
                unreadable = False
            except Exception as exc:
                log.error("get_pending_listing failed: %s", exc)
                listing, unreadable = None, True
            if listing is None:
                if once:
                    break
                await asyncio.sleep(POLL_SECONDS)
                continue

            log.info("Listing %s: %s (%s ILS)", listing["id"], listing["title"], listing["price"])
            run = await evaluate_listing(listing, mcp_tools, make_model(), similar)
            if run.fatal:
                fatal = run.fatal  # raised once the MCP sessions are closed
                break
            if run.saved:
                log.info("Listing %s evaluated: score %s, %s, confidence %s.", listing["id"],
                         run.saved["score"], run.saved["recommendation"], run.saved["confidence"])
            else:
                excluded[listing["id"]] = time.monotonic()
                log.warning("Listing %s stays Pending evaluation (%s); retried in %d min.",
                            listing["id"], "; ".join(run.errors), RETRY_AFTER_SECONDS // 60)
    if fatal:
        raise FatalAgentError(fatal)
    if unreadable:
        log.warning("Could not read the pending listings. Agent stopped; nothing was saved.")
    else:
        log.info("No more pending listings. Agent stopped.")


def main() -> int:
    parser = argparse.ArgumentParser(description="AI agent that evaluates pending listings")
    parser.add_argument("--once", action="store_true", help="evaluate what is pending now, then exit")
    once = parser.parse_args().once
    setup_logging()
    problems = startup_problems()
    if problems:
        for problem in problems:
            log.error(problem)
        return 1
    try:
        asyncio.run(run_agent(once=once))
    except KeyboardInterrupt:
        log.info("Agent stopped.")
    except FatalAgentError as exc:
        log.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
