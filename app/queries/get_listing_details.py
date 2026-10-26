"""Query: one listing's details, filtered by the viewer's role (read side — CQRS, F4)."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.listing import STATUS_REJECTED, Listing
from app.queries.listing_read_model import (
    ListingSummary,
    Viewer,
    select_listings_with_seller,
    to_summary,
    visible_to,
)


class ListingNotFoundError(Exception):
    """Raised when the listing does not exist or the viewer may not open it."""


@dataclass
class GetListingDetailsQuery:
    viewer: Viewer
    listing_id: str


@dataclass(frozen=True)
class ListingDetails:
    listing: ListingSummary
    rejection_reason: str | None
    # Only a moderator ever gets the agent's assessment section.
    show_assessment: bool


def handle_get_listing_details(session: Session, query: GetListingDetailsQuery) -> ListingDetails:
    viewer = query.viewer
    row = session.execute(
        select_listings_with_seller()
        .where(Listing.id == query.listing_id)
        .where(visible_to(viewer))
    ).first()
    if row is None:
        raise ListingNotFoundError("המודעה לא נמצאה או שאין לך הרשאה לצפות בה.")

    listing, seller_name = row
    is_owner = listing.seller_id == viewer.user_id
    rejection_reason = None
    if listing.status == STATUS_REJECTED and (is_owner or viewer.is_moderator):
        rejection_reason = listing.rejection_reason

    return ListingDetails(
        listing=to_summary(listing, seller_name),
        rejection_reason=rejection_reason,
        show_assessment=viewer.is_moderator,
    )
