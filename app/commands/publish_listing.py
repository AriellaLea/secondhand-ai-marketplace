"""Command: a seller publishes a listing (write side — CQRS + Event Sourcing)."""

import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.events.projections import project
from app.events.store import append_event
from app.events.types import LISTING_CREATED
from app.models.listing import CATEGORIES
from app.models.user import User

TITLE_MAX = 200
DESCRIPTION_MAX = 5000
PRICE_MAX = Decimal("99999999.99")  # fits Numeric(10, 2)


class PublishListingError(Exception):
    """Raised when the listing cannot be published."""


@dataclass
class PublishListingCommand:
    seller_id: int
    title: str
    description: str
    price: str
    category: str


def _parse_price(raw: str) -> Decimal:
    text = (raw or "").strip().replace(",", "")
    if not text:
        raise PublishListingError("נא להזין מחיר.")
    try:
        price = Decimal(text)
    except InvalidOperation:
        raise PublishListingError("המחיר חייב להיות מספר.") from None
    if not price.is_finite() or price <= 0:
        raise PublishListingError("המחיר חייב להיות מספר חיובי.")
    if price.as_tuple().exponent < -2:
        raise PublishListingError("המחיר יכול לכלול עד שתי ספרות אחרי הנקודה.")
    if price > PRICE_MAX:
        raise PublishListingError("המחיר גבוה מדי.")
    return price.quantize(Decimal("0.01"))


def handle_publish_listing(session: Session, cmd: PublishListingCommand) -> str:
    seller = session.get(User, cmd.seller_id)
    if seller is None or seller.role != "seller":
        raise PublishListingError("רק מוכרים יכולים לפרסם מודעות.")

    title = (cmd.title or "").strip()
    description = (cmd.description or "").strip()
    category = (cmd.category or "").strip()

    if not title:
        raise PublishListingError("נא להזין כותרת.")
    if len(title) > TITLE_MAX:
        raise PublishListingError(f"הכותרת יכולה להכיל עד {TITLE_MAX} תווים.")
    if not description:
        raise PublishListingError("נא להזין תיאור.")
    if len(description) > DESCRIPTION_MAX:
        raise PublishListingError(f"התיאור יכול להכיל עד {DESCRIPTION_MAX} תווים.")
    price = _parse_price(cmd.price)
    if category not in CATEGORIES:
        raise PublishListingError("נא לבחור קטגוריה מהרשימה.")

    listing_id = str(uuid.uuid4())
    event = append_event(
        session,
        listing_id=listing_id,
        event_type=LISTING_CREATED,
        payload={
            "title": title,
            "description": description,
            "price": str(price),
            "category": category,
        },
        actor_id=seller.id,
    )
    project(session, event)
    session.commit()  # event and read model are saved together or not at all
    return listing_id
