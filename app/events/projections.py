"""Projections: apply events to the read model (CQRS)."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.events.types import LISTING_CREATED
from app.models.event import Event
from app.models.listing import STATUS_PENDING_EVALUATION, Listing


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


_HANDLERS = {
    LISTING_CREATED: _apply_listing_created,
}


def project(session: Session, event: Event) -> None:
    handler = _HANDLERS.get(event.event_type)
    if handler is not None:
        handler(session, event)
