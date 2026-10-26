"""F6 – Dashboard (T-F6-1)."""

import re

import pytest

from app.models.listing import (
    CATEGORIES,
    STATUS_APPROVED,
    STATUS_EVALUATED,
    STATUS_LABELS,
    STATUS_PENDING_EVALUATION,
    STATUS_REJECTED,
    Listing,
)
from tests.conftest import login, make_listing, make_user


def _number(html, testid):
    match = re.search(rf'data-testid="{testid}">(\d+)<', html)
    assert match, testid
    return int(match.group(1))


@pytest.fixture
def seeded(db):
    alice = make_user(db, "alice@example.com", "seller")
    bob = make_user(db, "bob@example.com", "seller")
    make_user(db, "mod@example.com", "moderator")
    make_listing(db, alice, "1", STATUS_PENDING_EVALUATION, category="sports")
    make_listing(db, alice, "2", STATUS_PENDING_EVALUATION, category="sports")
    make_listing(db, alice, "3", STATUS_APPROVED, category="books")
    make_listing(db, bob, "4", STATUS_EVALUATED, category="sports")
    make_listing(db, bob, "5", STATUS_REJECTED, category="electronics")


def test_t_f6_1_counts_by_status_and_category(client, seeded):
    login(client, "mod@example.com")

    resp = client.get("/dashboard")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'dir="rtl"' in html
    assert _number(html, "total") == 5
    assert _number(html, f"status-{STATUS_PENDING_EVALUATION}") == 2
    assert _number(html, f"status-{STATUS_EVALUATED}") == 1
    assert _number(html, f"status-{STATUS_APPROVED}") == 1
    assert _number(html, f"status-{STATUS_REJECTED}") == 1
    assert _number(html, "category-sports") == 3
    assert _number(html, "category-books") == 1
    assert _number(html, "category-electronics") == 1
    assert _number(html, "category-furniture") == 0  # empty categories still shown


def test_t_f6_1_counts_match_listings_table(client, db, seeded):
    login(client, "mod@example.com")
    html = client.get("/dashboard").get_data(as_text=True)

    for status in STATUS_LABELS:
        table = client.get(f"/listings?status={status}").get_data(as_text=True)
        rows = table.count("<tr onclick=")
        assert _number(html, f"status-{status}") == rows, status
    for category in CATEGORIES:
        assert _number(html, f"category-{category}") == db.query(Listing).filter_by(category=category).count()


def test_counts_update_without_manual_step(client, db, seeded):
    login(client, "mod@example.com")
    before = _number(client.get("/dashboard").get_data(as_text=True), f"status-{STATUS_PENDING_EVALUATION}")

    login(client, "alice@example.com")
    client.post(
        "/listings",
        data={"title": "כיסא", "description": "כיסא עץ", "price": "80", "category": "furniture"},
    )

    login(client, "mod@example.com")
    html = client.get("/dashboard").get_data(as_text=True)
    assert _number(html, f"status-{STATUS_PENDING_EVALUATION}") == before + 1
    assert _number(html, "category-furniture") == 1


def test_empty_dashboard_shows_zeros(client, db):
    make_user(db, "mod@example.com", "moderator")
    login(client, "mod@example.com")

    html = client.get("/dashboard").get_data(as_text=True)

    assert _number(html, "total") == 0
    assert _number(html, "category-sports") == 0


def test_seller_cannot_open_dashboard(client, seeded):
    login(client, "alice@example.com")

    resp = client.get("/dashboard")

    assert resp.status_code == 302
    assert "/dashboard" not in resp.headers["Location"]
    assert "לוח בקרה" not in client.get("/listings").get_data(as_text=True)


def test_visitor_is_redirected_to_login(client, db):
    resp = client.get("/dashboard")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
