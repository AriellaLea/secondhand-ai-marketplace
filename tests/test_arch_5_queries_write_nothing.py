"""T-ARCH-5 – CQRS: loading search, details, table and dashboard pages writes nothing."""

import re

from sqlalchemy import event

from app.models.event import Event
from app.models.listing import STATUS_APPROVED, STATUS_PENDING_EVALUATION, Listing
from tests.conftest import login, make_listing, make_user

WRITE_SQL = re.compile(r"^\s*(INSERT|UPDATE|DELETE)\b", re.IGNORECASE)


def _snapshot(db):
    db.expire_all()
    events = [(e.id, e.event_type, e.listing_id, e.payload) for e in db.query(Event).order_by(Event.id)]
    listings = [(l.id, l.status, l.title, l.price) for l in db.query(Listing).order_by(Listing.id)]
    return events, listings


def test_t_arch_5_query_pages_do_not_write(app, client, db):
    alice = make_user(db, "alice@example.com", "seller")
    make_user(db, "mod@example.com", "moderator")
    login(client, "alice@example.com")
    # Publish through the real command so the events table is not empty.
    client.post(
        "/listings",
        data={"title": "אופניים", "description": "אופני הרים", "price": "450", "category": "sports"},
    )
    pending = db.query(Listing).filter_by(status=STATUS_PENDING_EVALUATION).one()
    approved = make_listing(db, alice, "ספה", STATUS_APPROVED)

    before = _snapshot(db)
    writes = []

    def record(conn, cursor, statement, *args):
        if WRITE_SQL.match(statement):
            writes.append(statement)

    event.listen(app.engine, "before_cursor_execute", record)
    try:
        for email in ["alice@example.com", "mod@example.com"]:
            login(client, email)
            urls = [
                "/listings/search",
                "/listings/search?q=אופני&category=sports",
                f"/listings/{approved.id}",
                f"/listings/{pending.id}",
                "/listings",
                "/listings?sort=price&dir=asc&status=approved",
            ]
            if email == "mod@example.com":
                urls.append("/dashboard")
            for url in urls:
                assert client.get(url).status_code == 200, url
    finally:
        event.remove(app.engine, "before_cursor_execute", record)

    assert writes == []
    assert _snapshot(db) == before
