"""Query: the listings table, sortable and filterable by status (read side — CQRS, F5)."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

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
    direction = query.direction if query.direction in ("asc", "desc") else DEFAULT_DIRECTION
    status = query.status if query.status in STATUS_LABELS else ""

    column = SORT_COLUMNS[sort]
    stmt = select_listings_with_seller().where(visible_to(query.viewer))
    if status:
        stmt = stmt.where(Listing.status == status)
    stmt = stmt.order_by(
        column.asc() if direction == "asc" else column.desc(),
        Listing.created_at.desc(),
        Listing.id,
    )

    rows = [to_summary(listing, seller_name) for listing, seller_name in session.execute(stmt)]
    return ListingsTable(rows=rows, sort=sort, direction=direction, status=status)
