"""Query: the event history of one listing, for moderators (read side — CQRS, F4/F8).

Read straight from the event store: it is the audit trail of who did what and when.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.events.types import LISTING_APPROVED, LISTING_CREATED, LISTING_EVALUATED, LISTING_REJECTED
from app.models.event import Event
from app.models.user import ROLE_AGENT, ROLE_MODERATOR, ROLE_SELLER, User

ISRAEL = ZoneInfo("Asia/Jerusalem")

EVENT_LABELS = {
    LISTING_CREATED: "נוצרה",
    LISTING_EVALUATED: "הוערכה",
    LISTING_APPROVED: "אושרה",
    LISTING_REJECTED: "נדחתה",
}
ROLE_LABELS = {
    ROLE_SELLER: "מוכר/ת",
    ROLE_MODERATOR: "מנהל/ת תוכן",
    ROLE_AGENT: "סוכן",
}


@dataclass(frozen=True)
class HistoryEntry:
    at: datetime  # Israel time
    event: str  # Hebrew label
    actor_name: str
    actor_role: str  # Hebrew label
    reason: str | None = None  # rejection reason


def _israel_time(moment: datetime) -> datetime:
    if moment.tzinfo is None:  # SQLite returns naive UTC
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(ISRAEL)


def listing_history(session: Session, listing_id: str) -> list[HistoryEntry]:
    rows = session.execute(
        select(Event, User.name, User.role)
        .join(User, User.id == Event.actor_id)
        .where(Event.listing_id == listing_id)
        .order_by(Event.id)
    ).all()
    return [
        HistoryEntry(
            at=_israel_time(event.created_at),
            event=EVENT_LABELS.get(event.event_type, event.event_type),
            actor_name=name,
            actor_role=ROLE_LABELS.get(role, role),
            reason=event.payload.get("reason") if event.event_type == LISTING_REJECTED else None,
        )
        for event, name, role in rows
    ]
