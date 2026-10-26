"""Query: the listings table, sortable and filterable by status (read side — CQRS, F5)."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.assessment import Assessment
from app.models.listing import STATUS_LABELS, Listing
from app.models.user import User
from app.queries.listing_read_model import (
    ListingSummary,
    Viewer,
    select_listings_with_seller,
    to_summary,
    visible_to,
)

SORT_COLUMNS = {
    "title": Listing.title,
    "seller": User.name,
    "category": Listing.category,
    "price": Listing.price,
    "status": Listing.status,
    "date": Listing.created_at,
    "score": Assessment.score,  # moderators only (sellers never see the score)
}
DEFAULT_SORT = "date"
DEFAULT_DIRECTION = "desc"


@dataclass
class ListListingsQuery:
    viewer: Viewer
    sort: str = DEFAULT_SORT
    direction: str = DEFAULT_DIRECTION
    status: str = ""


@dataclass(frozen=True)
class ListingsTable:
    rows: list[ListingSummary]
    sort: str
    direction: str
    status: str


def handle_list_listings(session: Session, query: ListListingsQuery) -> ListingsTable:
    sort = query.sort if query.sort in SORT_COLUMNS else DEFAULT_SORT
    if sort == "score" and not query.viewer.is_moderator:
        sort = DEFAULT_SORT
    direction = query.direction if query.direction in ("asc", "desc") else DEFAULT_DIRECTION
    status = query.status if query.status in STATUS_LABELS else ""

    column = SORT_COLUMNS[sort]
    stmt = select_listings_with_seller().where(visible_to(query.viewer))
    if status:
        stmt = stmt.where(Listing.status == status)
    stmt = stmt.order_by(
        # Not-yet-evaluated listings (no score) always come last.
        (column.asc() if direction == "asc" else column.desc()).nulls_last(),
        Listing.created_at.desc(),
        Listing.id,
    )

    # A seller never gets the agent score, not even in the DTO.
    show_score = query.viewer.is_moderator
    rows = [
        to_summary(listing, seller_name, score if show_score else None)
        for listing, seller_name, score in session.execute(stmt)
    ]
    return ListingsTable(rows=rows, sort=sort, direction=direction, status=status)
