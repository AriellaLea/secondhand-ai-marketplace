"""F5 – Listings table (T-F5-1, T-F5-2)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.listing import (
    STATUS_APPROVED,
    STATUS_EVALUATED,
    STATUS_PENDING_EVALUATION,
    STATUS_REJECTED,
)
from tests.conftest import login, make_listing, make_user

T0 = datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.fixture
def seeded(db):
    alice = make_user(db, "alice@example.com", "seller")
    bob = make_user(db, "bob@example.com", "seller")
    make_user(db, "mod@example.com", "moderator")
    make_listing(db, alice, "A-אושרה", STATUS_APPROVED, price="300", created_at=T0)
    make_listing(db, alice, "A-ממתינה", STATUS_PENDING_EVALUATION, price="100", created_at=T0 + timedelta(days=1))
    make_listing(db, alice, "A-נדחתה", STATUS_REJECTED, price="200", created_at=T0 + timedelta(days=2))
    make_listing(db, bob, "B-אושרה", STATUS_APPROVED, price="50", created_at=T0 + timedelta(days=3))
    make_listing(db, bob, "B-ממתינה", STATUS_PENDING_EVALUATION, price="400", created_at=T0 + timedelta(days=4))
    make_listing(db, bob, "B-הוערכה", STATUS_EVALUATED, price="500", created_at=T0 + timedelta(days=5))


def _order(html, titles):
    return sorted(titles, key=html.index)


def test_t_f5_1_seller_sees_others_approved_plus_all_own_newest_first(client, seeded):
    login(client, "alice@example.com")

    html = client.get("/listings").get_data(as_text=True)

    shown = ["A-אושרה", "A-ממתינה", "A-נדחתה", "B-אושרה"]
    for title in shown:
        assert title in html
    assert "B-ממתינה" not in html
    assert "B-הוערכה" not in html
    assert _order(html, shown) == ["B-אושרה", "A-נדחתה", "A-ממתינה", "A-אושרה"]
    # Statuses are shown; the agent score column is moderator-only.
    assert "ממתינה להערכה" in html
    assert "ציון הסוכן" not in html


def test_t_f5_2_moderator_sees_all_including_pending(client, seeded):
    login(client, "mod@example.com")

    html = client.get("/listings").get_data(as_text=True)

    for title in ["A-אושרה", "A-ממתינה", "A-נדחתה", "B-אושרה", "B-ממתינה", "B-הוערכה"]:
        assert title in html
    assert "ציון הסוכן" in html
    assert "טרם הוערכה" in html


def test_filter_by_status(client, seeded):
    login(client, "mod@example.com")

    html = client.get("/listings?status=pending_evaluation").get_data(as_text=True)

    assert "A-ממתינה" in html
    assert "B-ממתינה" in html
    assert "A-אושרה" not in html
    assert "B-הוערכה" not in html


def test_sort_by_price_ascending(client, seeded):
    login(client, "mod@example.com")

    html = client.get("/listings?sort=price&dir=asc").get_data(as_text=True)

    titles = ["A-אושרה", "A-ממתינה", "A-נדחתה", "B-אושרה", "B-ממתינה", "B-הוערכה"]
    assert _order(html, titles) == ["B-אושרה", "A-ממתינה", "A-נדחתה", "A-אושרה", "B-ממתינה", "B-הוערכה"]


def test_rows_link_to_details(client, db, seeded):
    from app.models.listing import Listing

    login(client, "alice@example.com")
    listing = db.query(Listing).filter_by(title="A-אושרה").one()

    html = client.get("/listings").get_data(as_text=True)

    assert f"/listings/{listing.id}" in html


def test_invalid_sort_and_status_fall_back_to_defaults(client, seeded):
    login(client, "mod@example.com")

    resp = client.get("/listings?sort=password_hash&dir=sideways&status=nope")

    assert resp.status_code == 200
    assert "B-הוערכה" in resp.get_data(as_text=True)


def test_publish_redirects_to_table(client, db):
    make_user(db, "carol@example.com", "seller")
    login(client, "carol@example.com")

    resp = client.post(
        "/listings",
        data={"title": "כיסא", "description": "כיסא עץ", "price": "80", "category": "furniture"},
    )

    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/listings")
