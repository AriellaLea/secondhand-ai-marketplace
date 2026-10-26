"""F4 – Listing details (T-F4-1, T-F4-2, T-F4-3, T-ROLE-1, T-ROLE-3)."""

import pytest

from app.models.listing import (
    STATUS_APPROVED,
    STATUS_EVALUATED,
    STATUS_PENDING_EVALUATION,
    STATUS_REJECTED,
)
from tests.conftest import login, make_listing, make_user

ASSESSMENT_HEADING = "הערכת הסוכן"


@pytest.fixture
def people(db):
    alice = make_user(db, "alice@example.com", "seller")
    bob = make_user(db, "bob@example.com", "seller")
    make_user(db, "mod@example.com", "moderator")
    return alice, bob


def test_t_f4_1_approved_listing_shows_all_details(client, db, people):
    alice, _ = people
    listing = make_listing(
        db, alice, "אופני הרים", STATUS_APPROVED,
        description="אופניים במצב מצוין", category="sports", price="450",
    )
    login(client, "bob@example.com")

    resp = client.get(f"/listings/{listing.id}")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert 'dir="rtl"' in html
    assert "אופני הרים" in html
    assert "אופניים במצב מצוין" in html
    assert "450.00" in html
    assert "ספורט" in html
    assert alice.name in html
    assert listing.created_at.strftime("%d/%m/%Y") in html
    assert "אושרה" in html


@pytest.mark.parametrize("status", [STATUS_PENDING_EVALUATION, STATUS_EVALUATED, STATUS_REJECTED])
def test_t_f4_2_seller_cannot_open_others_non_approved_listing(client, db, people, status):
    alice, _ = people
    listing = make_listing(db, alice, "מודעה סודית", status)
    login(client, "bob@example.com")

    # Not listed in Bob's pages, so there is nothing to click...
    assert "מודעה סודית" not in client.get("/listings").get_data(as_text=True)
    assert "מודעה סודית" not in client.get("/listings/search").get_data(as_text=True)
    # ...and typing the address directly is refused.
    resp = client.get(f"/listings/{listing.id}")
    assert resp.status_code == 404
    assert "מודעה סודית" not in resp.get_data(as_text=True)


@pytest.mark.parametrize("status", [STATUS_PENDING_EVALUATION, STATUS_EVALUATED, STATUS_REJECTED])
def test_seller_opens_own_listing_in_any_status(client, db, people, status):
    alice, _ = people
    listing = make_listing(db, alice, "המודעה שלי", status)
    login(client, "alice@example.com")

    assert client.get(f"/listings/{listing.id}").status_code == 200


def test_t_f4_3_seller_sees_rejection_reason_of_own_listing(client, db, people):
    alice, _ = people
    listing = make_listing(db, alice, "שעון", STATUS_REJECTED, rejection_reason="המחיר גבוה מדי ביחס לשוק")
    login(client, "alice@example.com")

    html = client.get(f"/listings/{listing.id}").get_data(as_text=True)

    assert "סיבת הדחייה" in html
    assert "המחיר גבוה מדי ביחס לשוק" in html


@pytest.mark.parametrize("email", ["alice@example.com", "bob@example.com"])
def test_t_role_1_seller_never_sees_assessment(client, db, people, email):
    alice, _ = people
    listing = make_listing(db, alice, "אופני הרים", STATUS_APPROVED)
    login(client, email)

    html = client.get(f"/listings/{listing.id}").get_data(as_text=True)

    assert ASSESSMENT_HEADING not in html


@pytest.mark.parametrize("status", [STATUS_PENDING_EVALUATION, STATUS_EVALUATED, STATUS_APPROVED, STATUS_REJECTED])
def test_moderator_opens_any_listing_with_assessment_section(client, db, people, status):
    alice, _ = people
    listing = make_listing(db, alice, "אופני הרים", status)
    login(client, "mod@example.com")

    resp = client.get(f"/listings/{listing.id}")

    assert resp.status_code == 200
    assert ASSESSMENT_HEADING in resp.get_data(as_text=True)


def test_unknown_listing_is_404(client, db, people):
    login(client, "alice@example.com")
    assert client.get("/listings/does-not-exist").status_code == 404


def test_visitor_is_redirected_to_login(client, db, people):
    alice, _ = people
    listing = make_listing(db, alice, "אופני הרים", STATUS_APPROVED)

    resp = client.get(f"/listings/{listing.id}")

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
