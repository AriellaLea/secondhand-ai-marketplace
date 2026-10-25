"""Event store: append-only. There is deliberately no update or delete."""

from sqlalchemy.orm import Session

from app.models.event import Event


def append_event(
    session: Session, listing_id: str, event_type: str, payload: dict, actor_id: int
) -> Event:
    event = Event(
        listing_id=listing_id,
        event_type=event_type,
        payload=payload,
        actor_id=actor_id,
    )
    session.add(event)
    session.flush()  # assigns id and created_at without committing
    return event
