"""Query: the next listing waiting for the AI agent (read side — CQRS, phase 7 MCP tool)."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.listing import STATUS_PENDING_EVALUATION, Listing


@dataclass
class GetPendingListingQuery:
    # Listings the agent already failed on during this run, so one bad listing
    # does not block the queue. Empty again when the agent restarts.
    exclude_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PendingListing:
    id: str
    title: str
    description: str
    price: Decimal  # ILS
    category: str
    created_at: datetime


def handle_get_pending_listing(session: Session, query: GetPendingListingQuery) -> PendingListing | None:
    """Oldest listing in status Pending evaluation first (FIFO). Nothing is locked or written."""
    stmt = select(Listing).where(Listing.status == STATUS_PENDING_EVALUATION)
    if query.exclude_ids:
        stmt = stmt.where(Listing.id.not_in(query.exclude_ids))
    listing = session.scalars(stmt.order_by(Listing.created_at, Listing.id).limit(1)).first()
    if listing is None:
        return None
    return PendingListing(
        id=listing.id,
        title=listing.title,
        description=listing.description,
        price=listing.price,
        category=listing.category,
        created_at=listing.created_at,
    )
