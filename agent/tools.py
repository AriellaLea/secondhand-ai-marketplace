"""The tools the agent's LLM sees for one listing, and the guards around them.

The program, not the LLM, decides what may be saved: save_assessment is refused
unless the similar-listing search ran and a web search found results. The model only
reports the web prices it read and whether the description is about the item in the
title; it never sees the listing price (it picked web prices close to it) and writes
no text (a small model slips other scripts into Hebrew). The program keeps the web prices that
really appear in the results (a small model copies or invents prices), computes the
three sub-scores and writes their Hebrew reasons and the reasoning (app/pricing.py,
app/listing_quality.py), and fills in the listing id and the similar listing ids
(a small model invents ids).
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from langchain_core.tools import BaseTool, StructuredTool

from agent.config import (
    QUERY_WORD_MIN_LETTERS,
    SIMILAR_K,
    SIMILARITY_MIN,
    TAVILY_MAX_RESULTS,
    TAVILY_MAX_SEARCHES,
    TAVILY_OUTPUT_MAX_CHARS,
)
from app.commands.record_assessment import recommendation_for
from app.listing_quality import score_quality
from app.pricing import build_reasoning, score_vs_market, score_vs_similar
from app.vector_store import find_similar_listings

log = logging.getLogger("agent")

# Without this account nothing can ever be saved: the process stops (see __main__).
MISSING_AGENT_ACCOUNT = "create_agent_user"

# A number as written on a web page: 2490, 2,490, 2.490, 1,290.00, 27.5
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_THOUSANDS = re.compile(r"\d{1,3}(?:[.,]\d{3})+")
_WITH_DECIMALS = re.compile(r"(\d+(?:[.,]\d{3})*)[.,](\d{1,2})")

# What the model sees of save_assessment; the program fills in everything else.
SAVE_SCHEMA = {
    "type": "object",
    "properties": {
        "web_prices": {
            "type": "array",
            "items": {"type": "number"},
            "description": "Every price in ILS of this item that you read in the web results, copied exactly.",
        },
        "description_matches_title": {
            "type": "boolean",
            "description": "Is the description about the item named in the title? true or false.",
        },
    },
    "required": ["web_prices", "description_matches_title"],
}
SAVE_DESCRIPTION = (
    "Save your assessment of the listing. The program checks your web prices, scores the price "
    "and writes the reasoning. Call it once, after reading the results of the other tools."
)


@dataclass
class ListingRun:
    """What happened while evaluating one listing."""

    listing: dict
    rag_done: bool = False
    rag_ids: list[str] = field(default_factory=list)
    rag_prices: list[Decimal] = field(default_factory=list)
    searches: int = 0
    web_ok: bool = False
    web_text: str = ""  # every web result the model read
    price_hint_given: bool = False  # told once to search again when no price was verified
    save_too_early: bool = False  # save_assessment called together with other tools
    saved: dict | None = None
    fatal: str | None = None
    errors: list[str] = field(default_factory=list)

    def can_still_save(self) -> bool:
        """Both searches succeeded and no guard has given up on this listing."""
        return self.saved is None and self.fatal is None and self.rag_done and self.web_ok

    def fail(self, reason: str) -> str:
        self.errors.append(reason)
        log.warning("  %s", reason)
        return reason


def text_of(content: Any) -> str:
    """Text of an MCP tool result (a string or a list of content blocks)."""
    if isinstance(content, str):
        return content
    return "\n".join(
        block.get("text", "") if isinstance(block, dict) else str(block) for block in content or []
    )


async def call_mcp(tool: BaseTool, args: dict) -> tuple[str, Any]:
    """Call an MCP tool; returns (text, structured content). Raises ToolException on a tool error."""
    message = await tool.ainvoke({"type": "tool_call", "id": "program", "name": tool.name, "args": args})
    artifact = message.artifact
    structured = artifact.get("structured_content") if isinstance(artifact, dict) else None
    if isinstance(structured, dict) and set(structured) == {"result"}:
        structured = structured["result"]  # FastMCP wraps optional results
    return text_of(message.content), structured


def prices_in_text(text: str) -> set[Decimal]:
    """Every number of the text, read the ways a page may write a price."""
    found = set()
    for token in _NUMBER.findall(text):
        if token.isdigit():
            found.add(Decimal(token))
        if _THOUSANDS.fullmatch(token):
            found.add(Decimal(re.sub(r"[.,]", "", token)))
        decimals = _WITH_DECIMALS.fullmatch(token)
        if decimals:
            found.add(Decimal(re.sub(r"[.,]", "", decimals[1]) + "." + decimals[2]))
    return found


def verified_prices(reported, text: str) -> tuple[list[Decimal], list]:
    """(prices that appear in the text, the other values sent)."""
    in_text = prices_in_text(text)
    kept, ignored = [], []
    for value in reported if isinstance(reported, list) else [reported]:
        price = _number_from(value)
        if price is not None and price.is_finite() and price > 0 and price in in_text:
            kept.append(price)
        else:
            ignored.append(value)
    return kept, ignored


def query_mentions_title(query: str, title: str) -> bool:
    words = [word for word in re.findall(r"\w+", title.lower()) if len(word) >= QUERY_WORD_MIN_LETTERS]
    return any(word in query.lower() for word in words)


def _number_from(value) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("₪", "").strip())
    except InvalidOperation:
        return None


def _yes_no(value) -> bool | None:
    if isinstance(value, bool):
        return value
    return {"true": True, "false": False}.get(str(value).strip().lower())


def _number(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _web_results_found(text: str) -> bool:
    # tavily-mcp reports some API failures as plain text, not as a tool error.
    return "Tavily API error" not in text and "Detailed Results:" in text and "URL:" in text


def build_tools(
    run: ListingRun,
    mcp_tools: dict[str, BaseTool],
    similar: Callable = find_similar_listings,
) -> list[BaseTool]:
    listing = run.listing

    async def search_similar_listings() -> str:
        try:
            found = await asyncio.to_thread(
                similar, listing["title"], listing["description"], k=SIMILAR_K, exclude_id=listing["id"]
            )
        except Exception as exc:  # Ollama or Chroma down
            return run.fail(f"Similar-listing search failed ({exc}). Do not call save_assessment; stop.")
        run.rag_done = True
        close = [item for item in found if item.similarity >= SIMILARITY_MIN]
        run.rag_ids = [item.listing_id for item in close]
        run.rag_prices = [Decimal(str(item.price)) for item in close]
        log.info("  similar listings: %s", ", ".join(run.rag_ids) or "none")
        if not close:
            return "No similar listing found."
        return "Similar listings (id | title | price in ILS | category):\n" + "\n".join(
            f"{item.listing_id} | {item.title} | {item.price:.0f} | {item.category}" for item in close
        )

    async def tavily_search(query: str) -> str:
        if run.searches >= TAVILY_MAX_SEARCHES:
            return "Search limit reached. Use the results you already have."
        if not query_mentions_title(query, listing["title"]):
            return (f"Search refused: write the query with words of the listing title "
                    f"({listing['title']}), not of a similar listing. Search again.")
        run.searches += 1
        try:
            text, _ = await call_mcp(
                mcp_tools["tavily_search"],
                {"query": query, "max_results": TAVILY_MAX_RESULTS, "search_depth": "basic", "country": "israel"},
            )
        except Exception as exc:  # tool error, network down, server crashed
            return run.fail(f"Web search failed ({exc}). Do not call save_assessment; stop.")
        if not _web_results_found(text):
            return run.fail(f"Web search found no usable results: {text[:300]}")
        run.web_ok = True
        text = text[:TAVILY_OUTPUT_MAX_CHARS]
        run.web_text += text + "\n"  # what the model read: its prices are checked against it
        return text

    mcp_save = mcp_tools["save_assessment"]

    async def save_assessment(**kwargs) -> str:
        if run.saved:
            return "The assessment is already saved. Stop now."
        if run.save_too_early:
            run.save_too_early = False
            return ("Not saved: you called save_assessment before reading the results of the other tools. "
                    "Read them, then call save_assessment again.")
        if not run.rag_done:
            return "Not saved: call search_similar_listings first."
        if not run.web_ok:
            return run.fail("Not saved: no web search succeeded for this listing. Stop now.")
        missing = [name for name in SAVE_SCHEMA["required"] if kwargs.get(name) is None]
        if missing:
            return run.fail(f"Not saved: add {', '.join(missing)}. Call save_assessment again.")
        matches = _yes_no(kwargs["description_matches_title"])
        if matches is None:
            return "Not saved: description_matches_title must be true or false. Call save_assessment again."
        quality = score_quality(listing["description"], matches)

        web_prices, ignored = verified_prices(kwargs["web_prices"], run.web_text)
        if ignored:
            log.info("  web prices not found in the results, ignored: %s", ", ".join(map(str, ignored)))
        if not web_prices and not run.price_hint_given and run.searches < TAVILY_MAX_SEARCHES:
            run.price_hint_given = True
            return ("Not saved: none of web_prices appears in the web results. Call tavily_search again "
                    "with other words, then call save_assessment with the prices written in the results.")

        price = Decimal(str(listing["price"]))
        market = score_vs_market(price, web_prices)
        vs_similar = score_vs_similar(price, run.rag_prices)
        score = market.points + vs_similar.points + quality.points
        args = {
            "listing_id": listing["id"],
            "price_vs_market": market.points,
            "price_vs_market_reason": market.reason,
            "price_vs_similar": vs_similar.points,
            "price_vs_similar_reason": vs_similar.reason,
            "listing_quality": quality.points,
            "listing_quality_reason": quality.reason,
            "market_price_min": _number(market.lowest),
            "market_price_max": _number(market.highest),
            "market_price_new": _number(market.new_price),
            "similar_listing_ids": run.rag_ids,
            "reasoning": build_reasoning(
                [market.reason, vs_similar.reason, quality.reason], recommendation_for(score)
            ),
        }
        try:
            _, result = await call_mcp(mcp_save, args)
        except Exception as exc:
            if MISSING_AGENT_ACCOUNT in str(exc):
                run.fatal = str(exc)
            return run.fail(f"Not saved: {exc}")
        run.saved = result
        return f"Saved: score {result['score']}, recommendation {result['recommendation']}. Stop now."

    return [
        StructuredTool.from_function(
            coroutine=search_similar_listings,
            name="search_similar_listings",
            description="Find listings similar to the one you evaluate, with their prices. No arguments.",
        ),
        StructuredTool.from_function(
            coroutine=tavily_search,
            name="tavily_search",
            description="Search the web for the market price of an item. Returns titles, URLs and text.",
        ),
        StructuredTool.from_function(
            coroutine=save_assessment,
            name="save_assessment",
            description=SAVE_DESCRIPTION,
            args_schema=SAVE_SCHEMA,
        ),
    ]

