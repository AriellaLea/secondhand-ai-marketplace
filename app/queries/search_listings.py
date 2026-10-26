"""Query: search listings by keyword and category (read side — CQRS, F3)."""

from dataclasses import dataclass

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.listing import CATEGORIES, STATUS_APPROVED, Listing
from app.queries.listing_read_model import (
    ListingSummary,
    Viewer,
    select_listings_with_seller,
    to_summary,
)


@dataclass
class SearchListingsQuery:
    viewer: Viewer
    keyword: str = ""
    category: str = ""


def _like_pattern(keyword: str) -> str:
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def handle_search_listings(session: Session, query: SearchListingsQuery) -> list[ListingSummary]:
    keyword = (query.keyword or "").strip()
    category = (query.category or "").strip()

    stmt = select_listings_with_seller()
    # A seller searches Approved listings only; a moderator searches every status.
    if not query.viewer.is_moderator:
        stmt = stmt.where(Listing.status == STATUS_APPROVED)
    if keyword:
        pattern = _like_pattern(keyword)
        stmt = stmt.where(
            or_(
                Listing.title.ilike(pattern, escape="\\"),
                Listing.description.ilike(pattern, escape="\\"),
            )
        )
    if category in CATEGORIES:
        stmt = stmt.where(Listing.category == category)
    stmt = stmt.order_by(Listing.created_at.desc(), Listing.id)

    # A seller never gets the agent score, not even in the DTO.
    show_score = query.viewer.is_moderator
    return [
        to_summary(listing, seller_name, score if show_score else None)
        for listing, seller_name, score in session.execute(stmt)
    ]
