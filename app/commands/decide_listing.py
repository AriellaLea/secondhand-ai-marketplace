"""Commands: a moderator approves or rejects an evaluated listing (write side — CQRS + Event Sourcing, F8).

A decision is final and only an Evaluated listing can get one. The listing row is
locked while the rule is checked, so two moderators deciding at the same time
cannot both succeed.
"""

import logging
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.events.projections import project
from app.events.store import append_event
from app.events.types import LISTING_APPROVED, LISTING_REJECTED
from app.models.listing import STATUS_EVALUATED, STATUS_PENDING_EVALUATION, Listing
from app.models.user import ROLE_MODERATOR, User
from app.vector_store import ListingDocument, index_listings

log = logging.getLogger(__name__)

REASON_MIN = 5
REASON_MAX = 1000


class DecideListingError(Exception):
    """Raised when the decision cannot be recorded; nothing was saved."""


@dataclass
class ApproveListingCommand:
    moderator_id: int
    listing_id: str


@dataclass
class RejectListingCommand:
    moderator_id: int
    listing_id: str
    reason: str


@dataclass(frozen=True)
class ApprovedListing:
    listing_id: str
    indexed: bool  # added to the vector database; False if Ollama or Chroma failed


def index_approved_listing(listing: Listing) -> None:
    """Add an approved listing to the vector database, so the agent can compare with it."""
    index_listings([
        ListingDocument(
            listing_id=listing.id,
            title=listing.title,
            description=listing.description,
            category=listing.category,
            price=float(listing.price),
            source="approved",
        )
    ])


def _evaluated_listing(session: Session, moderator_id: int, listing_id: str) -> tuple[User, Listing]:
    moderator = session.get(User, moderator_id)
    if moderator is None or moderator.role != ROLE_MODERATOR:
        raise DecideListingError("רק מנהלי תוכן יכולים לאשר או לדחות מודעות.")
    # Locked until commit: a second decision waits, then sees the new status.
    listing = session.get(Listing, (listing_id or "").strip(), with_for_update=True)
    if listing is None:
        raise DecideListingError("המודעה לא נמצאה.")
    if listing.status == STATUS_PENDING_EVALUATION:
        raise DecideListingError("לא ניתן להחליט על מודעה שהסוכן טרם העריך.")
    if listing.status != STATUS_EVALUATED:
        raise DecideListingError("המודעה כבר טופלה.")
    return moderator, listing


def handle_approve_listing(
    session: Session,
    cmd: ApproveListingCommand,
    index: Callable[[Listing], None] = index_approved_listing,
) -> ApprovedListing:
    moderator, listing = _evaluated_listing(session, cmd.moderator_id, cmd.listing_id)
    event = append_event(
        session, listing_id=listing.id, event_type=LISTING_APPROVED, payload={}, actor_id=moderator.id
    )
    project(session, event)
    session.commit()  # event and read model are saved together or not at all

    # The approval stands even if Ollama is down; scripts/index_approved_listings.py catches up.
    try:
        index(listing)
    except Exception as exc:
        log.warning("Approved listing %s not added to the vector database: %s", listing.id, exc)
        return ApprovedListing(listing.id, indexed=False)
    return ApprovedListing(listing.id, indexed=True)


def handle_reject_listing(session: Session, cmd: RejectListingCommand) -> str:
    reason = (cmd.reason or "").strip()
    if len(reason) < REASON_MIN:
        raise DecideListingError(f"נא לכתוב סיבת דחייה של {REASON_MIN} תווים לפחות.")
    if len(reason) > REASON_MAX:
        raise DecideListingError(f"סיבת הדחייה יכולה להכיל עד {REASON_MAX} תווים.")
    moderator, listing = _evaluated_listing(session, cmd.moderator_id, cmd.listing_id)
    event = append_event(
        session, listing_id=listing.id, event_type=LISTING_REJECTED, payload={"reason": reason},
        actor_id=moderator.id,
    )
    project(session, event)
    session.commit()
    return listing.id
