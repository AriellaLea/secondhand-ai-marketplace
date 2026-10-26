"""Shared read-side helpers for listing queries: viewer, visibility rule, row DTO."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, or_, select, true

from app.models.listing import STATUS_APPROVED, Listing
from app.models.user import User


@dataclass(frozen=True)
class Viewer:
    user_id: int
    role: str  # seller | moderator

    @property
    def is_moderator(self) -> bool:
        return self.role == "moderator"


@dataclass(frozen=True)
class ListingSummary:
    id: str
    title: str
    description: str
    category: str
    price: Decimal
    status: str
    seller_id: int
    seller_name: str
    created_at: datetime
    score: int | None = None  # filled from the assessments read model once F7 exists


def visible_to(viewer: Viewer):
    """A moderator sees every listing; a seller sees Approved listings plus their own."""
    if viewer.is_moderator:
        return true()
    return or_(Listing.status == STATUS_APPROVED, Listing.seller_id == viewer.user_id)


def select_listings_with_seller() -> Select:
    return select(Listing, User.name).join(User, User.id == Listing.seller_id)


def to_summary(listing: Listing, seller_name: str) -> ListingSummary:
    return ListingSummary(
        id=listing.id,
        title=listing.title,
        description=listing.description,
        category=listing.category,
        price=listing.price,
        status=listing.status,
        seller_id=listing.seller_id,
        seller_name=seller_name,
        created_at=listing.created_at,
    )
