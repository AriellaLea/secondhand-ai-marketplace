"""F2 – Publish a listing (T-F2-1, T-F2-2, T-ARCH-1)."""

from decimal import Decimal

import pytest

from app.events.types import LISTING_CREATED
from app.models.event import Event
from app.models.listing import STATUS_PENDING_EVALUATION, Listing
from tests.conftest import login, make_user

VALID = {
    "title": "אופניים",
    "description": "אופני הרים במצב טוב",
    "price": "450",
    "category": "sports",
}


def test_t_f2_1_seller_publishes_listing_pending_evaluation(client, db):
    seller = make_user(db, "seller@example.com", "seller")
    login(client, "seller@example.com")

    resp = client.post("/listings", data=VALID)

    assert resp.status_code == 302
    listing = db.query(Listing).one()
    assert listing.status == STATUS_PENDING_EVALUATION
    assert listing.seller_id == seller.id
    assert listing.title == "אופניים"
    assert listing.price == Decimal("450.00")
    assert listing.category == "sports"


def test_t_arch_1_listing_created_event_with_seller_as_actor(client, db):
    seller = make_user(db, "seller@example.com", "seller")
    login(client, "seller@example.com")

    client.post("/listings", data=VALID)

    event = db.query(Event).one()
    listing = db.query(Listing).one()
    assert event.event_type == LISTING_CREATED
    assert event.actor_id == seller.id
    assert event.listing_id == listing.id
    assert event.payload["price"] == "450.00"


@pytest.mark.parametrize(
    "override",
    [
        {"title": ""},
        {"description": "   "},
        {"price": ""},
        {"price": "-10"},
        {"price": "0"},
        {"price": "abc"},
        {"category": ""},
        {"category": "cars"},
    ],
)
def test_t_f2_2_invalid_form_is_refused_and_nothing_saved(client, db, override):
    make_user(db, "seller@example.com", "seller")
    login(client, "seller@example.com")

    resp = client.post("/listings", data={**VALID, **override})

    assert resp.status_code == 400
    assert db.query(Listing).count() == 0
    assert db.query(Event).count() == 0


def test_moderator_cannot_publish(client, db):
    make_user(db, "mod@example.com", "moderator")
    login(client, "mod@example.com")

    assert client.get("/listings/new").status_code == 302
    client.post("/listings", data=VALID)
    assert db.query(Event).count() == 0


def test_visitor_is_redirected_to_login(client, db):
    resp = client.get("/listings/new")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_form_is_hebrew_rtl(client, db):
    make_user(db, "seller@example.com", "seller")
    login(client, "seller@example.com")

    html = client.get("/listings/new").get_data(as_text=True)
    assert 'dir="rtl"' in html
    assert "פרסום מודעה" in html
