"""Our own MCP tools for the AI agent (phase 7): get a pending listing, save an assessment.

Thin adapter, like a controller: each tool opens a DB session, calls one query or
command handler and returns plain JSON. No business rules live here.

Run over stdio (the agent starts it as a subprocess):
    python -m app.mcp_tools.server
Inspect it by hand:
    npx @modelcontextprotocol/inspector .venv/bin/python -m app.mcp_tools.server
"""

from contextlib import contextmanager
from typing_extensions import TypedDict  # pydantic needs this one on Python < 3.12

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.commands.record_assessment import (
    RecordAssessmentCommand,
    RecordAssessmentError,
    handle_record_assessment,
)
from app.queries.get_pending_listing import GetPendingListingQuery, handle_get_pending_listing

mcp = FastMCP(
    "secondhand-marketplace",
    instructions=(
        "Tools to evaluate second-hand listings. Call get_pending_listing to fetch the next "
        "listing, assess it, then call save_assessment once for that listing. You never "
        "approve or reject a listing: a human moderator decides."
    ),
)



class PendingListingResult(TypedDict):
    id: str
    title: str
    description: str
    price: float  # ILS
    category: str
    created_at: str  # ISO 8601


class SavedAssessmentResult(TypedDict):
    listing_id: str
    score: int  # 0-100, sum of the three sub-scores
    recommendation: str  # approve | manual_review | reject
    confidence: str  # low | medium | high
    status: str  # evaluated


_session_factory: sessionmaker | None = None


def configure(engine: Engine) -> None:
    """Use this engine for every tool call (tests pass a SQLite engine)."""
    global _session_factory
    _session_factory = sessionmaker(bind=engine)


def _default_engine() -> Engine:
    from app.config import Config
    from app.db import Base
    from app.models import assessment, event, listing, user  # noqa: F401  register tables

    # pool_pre_ping: Neon closes idle connections, the agent may idle for a while.
    engine = create_engine(Config.DATABASE_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    return engine


@contextmanager
def _session() -> Session:
    if _session_factory is None:
        configure(_default_engine())
    session = _session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@mcp.tool()
def get_pending_listing(exclude_ids: list[str] | None = None) -> PendingListingResult | None:
    """Get the next listing waiting for evaluation (status Pending evaluation), oldest first.

    Returns the listing's id, title, description, price (in ILS), category and
    created_at, or null when no listing is waiting. Pass in exclude_ids the ids of
    listings you could not evaluate in this run, to skip them.
    """
    with _session() as session:
        listing = handle_get_pending_listing(
            session, GetPendingListingQuery(exclude_ids=exclude_ids or [])
        )
    if listing is None:
        return None
    return {
        "id": listing.id,
        "title": listing.title,
        "description": listing.description,
        "price": float(listing.price),
        "category": listing.category,
        "created_at": listing.created_at.isoformat(),
    }


@mcp.tool()
def save_assessment(
    listing_id: str,
    price_vs_market: int,
    price_vs_market_reason: str,
    price_vs_similar: int,
    price_vs_similar_reason: str,
    listing_quality: int,
    listing_quality_reason: str,
    market_price_min: float,
    market_price_max: float,
    similar_listing_ids: list[str],
    reasoning: str,
) -> SavedAssessmentResult:
    """Save your assessment of one listing. The listing then moves to status Evaluated.

    Only call this when you have everything below; if the web search or anything
    else failed, do not call it, and the listing will be evaluated again later.

    - listing_id: the id returned by get_pending_listing.
    - price_vs_market (0-50): listing price compared with the market price range found on the web.
    - price_vs_similar (0-25): listing price compared with the prices of similar listings.
    - listing_quality (0-25): title, description and category are consistent and detailed.
    - each *_reason: one line explaining that sub-score.
    - market_price_min, market_price_max: market price range found on the web, in ILS.
    - similar_listing_ids: ids of the similar listings found in the vector database (may be empty).
    - reasoning: a short reasoning in Hebrew for the moderator.

    Do not compute the total score or the recommendation: the program does it and
    returns score, recommendation and confidence.
    """
    cmd = RecordAssessmentCommand(
        listing_id=listing_id,
        price_vs_market=price_vs_market,
        price_vs_market_reason=price_vs_market_reason,
        price_vs_similar=price_vs_similar,
        price_vs_similar_reason=price_vs_similar_reason,
        listing_quality=listing_quality,
        listing_quality_reason=listing_quality_reason,
        market_price_min=market_price_min,
        market_price_max=market_price_max,
        similar_listing_ids=similar_listing_ids,
        reasoning=reasoning,
    )
    try:
        with _session() as session:
            result = handle_record_assessment(session, cmd)
    except RecordAssessmentError as exc:
        raise ToolError(str(exc)) from None
    return {
        "listing_id": result.listing_id,
        "score": result.score,
        "recommendation": result.recommendation,
        "confidence": result.confidence,
        "status": result.status,
    }


if __name__ == "__main__":
    mcp.run()  # stdio transport
