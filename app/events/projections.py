"""Projections: apply events to the read model (CQRS)."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.events.types import LISTING_CREATED, LISTING_EVALUATED
from app.models.assessment import Assessment
from app.models.event import Event
from app.models.listing import STATUS_EVALUATED, STATUS_PENDING_EVALUATION, Listing


def _apply_listing_created(session: Session, event: Event) -> None:
    data = event.payload
    session.add(
        Listing(
            id=event.listing_id,
            seller_id=event.actor_id,
            title=data["title"],
            description=data["description"],
            category=data["category"],
            price=Decimal(data["price"]),
            status=STATUS_PENDING_EVALUATION,
            created_at=event.created_at,
        )
    )


def _apply_listing_evaluated(session: Session, event: Event) -> None:
    data = event.payload
    session.add(
        Assessment(
            listing_id=event.listing_id,
            score=data["score"],
            price_vs_market=data["price_vs_market"],
            price_vs_market_reason=data["price_vs_market_reason"],
            price_vs_similar=data["price_vs_similar"],
            price_vs_similar_reason=data["price_vs_similar_reason"],
            listing_quality=data["listing_quality"],
            listing_quality_reason=data["listing_quality_reason"],
            recommendation=data["recommendation"],
            confidence=data["confidence"],
            market_price_min=Decimal(data["market_price_min"]),
            market_price_max=Decimal(data["market_price_max"]),
            similar_listing_ids=data["similar_listing_ids"],
            reasoning=data["reasoning"],
            evaluated_at=event.created_at,
        )
    )
    session.get(Listing, event.listing_id).status = STATUS_EVALUATED


_HANDLERS = {
    LISTING_CREATED: _apply_listing_created,
    LISTING_EVALUATED: _apply_listing_evaluated,
}


def project(session: Session, event: Event) -> None:
    handler = _HANDLERS.get(event.event_type)
    if handler is not None:
        handler(session, event)
