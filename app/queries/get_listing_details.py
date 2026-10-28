"""Query: one listing's details, filtered by the viewer's role (read side — CQRS, F4)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.assessment import Assessment
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
class AssessmentView:
    score: int
    price_vs_market: int
    price_vs_market_reason: str
    price_vs_similar: int
    price_vs_similar_reason: str
    listing_quality: int
    listing_quality_reason: str
    recommendation: str
    confidence: str
    market_price_min: Decimal | None  # None when no price was found on the web
    market_price_max: Decimal | None
    market_price_new: Decimal | None  # also None in assessments made before it existed
    similar_listing_ids: list[str]
    reasoning: str
    evaluated_at: datetime


@dataclass(frozen=True)
class ListingDetails:
    listing: ListingSummary
    rejection_reason: str | None
    # Only a moderator ever gets the agent's assessment section.
    show_assessment: bool
    assessment: AssessmentView | None = None  # None for sellers, or while not evaluated yet


def _assessment_view(assessment: Assessment) -> AssessmentView:
    return AssessmentView(
        score=assessment.score,
        price_vs_market=assessment.price_vs_market,
        price_vs_market_reason=assessment.price_vs_market_reason,
        price_vs_similar=assessment.price_vs_similar,
        price_vs_similar_reason=assessment.price_vs_similar_reason,
        listing_quality=assessment.listing_quality,
        listing_quality_reason=assessment.listing_quality_reason,
        recommendation=assessment.recommendation,
        confidence=assessment.confidence,
        market_price_min=assessment.market_price_min,
        market_price_max=assessment.market_price_max,
        market_price_new=assessment.market_price_new,
        similar_listing_ids=list(assessment.similar_listing_ids),
        reasoning=assessment.reasoning,
        evaluated_at=assessment.evaluated_at,
    )


def handle_get_listing_details(session: Session, query: GetListingDetailsQuery) -> ListingDetails:
    viewer = query.viewer
    row = session.execute(
        select_listings_with_seller()
        .where(Listing.id == query.listing_id)
        .where(visible_to(viewer))
    ).first()
    if row is None:
        raise ListingNotFoundError("המודעה לא נמצאה או שאין לך הרשאה לצפות בה.")

    listing, seller_name, score = row
    is_owner = listing.seller_id == viewer.user_id
    rejection_reason = None
    if listing.status == STATUS_REJECTED and (is_owner or viewer.is_moderator):
        rejection_reason = listing.rejection_reason

    assessment = None
    if viewer.is_moderator:
        stored = session.get(Assessment, listing.id)
        if stored is not None:
            assessment = _assessment_view(stored)

    return ListingDetails(
        # A seller never gets the agent score, not even in the DTO.
        listing=to_summary(listing, seller_name, score if viewer.is_moderator else None),
        rejection_reason=rejection_reason,
        show_assessment=viewer.is_moderator,
        assessment=assessment,
    )
