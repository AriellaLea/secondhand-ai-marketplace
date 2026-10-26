"""F3 – Search listings (T-F3-1, T-F3-2, T-F3-3)."""

from app.models.listing import STATUS_APPROVED, STATUS_PENDING_EVALUATION, STATUS_REJECTED
from tests.conftest import login, make_listing, make_user


def _seed(db):
    alice = make_user(db, "alice@example.com", "seller")
    bob = make_user(db, "bob@example.com", "seller")
    make_listing(db, alice, "אופני הרים", STATUS_APPROVED, category="sports")
    make_listing(db, bob, "ספה תלת מושבית", STATUS_APPROVED, description="ספה נוחה כמו אופניים", category="furniture")
    make_listing(db, bob, "מחשב נייד", STATUS_APPROVED, category="electronics")
    make_listing(db, bob, "אופניים חשמליים", STATUS_PENDING_EVALUATION, category="sports")
    make_listing(db, bob, "אופני ילדים", STATUS_REJECTED, category="sports")
    return alice, bob


def test_t_f3_1_search_by_word_in_title_or_description(client, db):
    _seed(db)
    login(client, "alice@example.com")

    html = client.get("/listings/search?q=אופני").get_data(as_text=True)

    assert "אופני הרים" in html
    assert "ספה תלת מושבית" in html  # match in the description
    assert "מחשב נייד" not in html


def test_t_f3_1_seller_sees_only_approved_in_search(client, db):
    _seed(db)
    login(client, "bob@example.com")

    html = client.get("/listings/search?q=אופני").get_data(as_text=True)

    assert "אופניים חשמליים" not in html  # Bob's own, but Pending evaluation
    assert "אופני ילדים" not in html


def test_moderator_searches_every_status(client, db):
    _seed(db)
    make_user(db, "mod@example.com", "moderator")
    login(client, "mod@example.com")

    html = client.get("/listings/search?q=אופני").get_data(as_text=True)

    assert "אופניים חשמליים" in html
    assert "אופני ילדים" in html


def test_t_f3_2_filter_by_category(client, db):
    _seed(db)
    login(client, "alice@example.com")

    html = client.get("/listings/search?category=furniture").get_data(as_text=True)

    assert "ספה תלת מושבית" in html
    assert "אופני הרים" not in html
    assert "מחשב נייד" not in html


def test_keyword_and_category_combined(client, db):
    _seed(db)
    login(client, "alice@example.com")

    html = client.get("/listings/search?q=אופני&category=sports").get_data(as_text=True)

    assert "אופני הרים" in html
    assert "ספה תלת מושבית" not in html


def test_t_f3_3_no_match_shows_empty_message(client, db):
    _seed(db)
    login(client, "alice@example.com")

    resp = client.get("/listings/search?q=טלסקופ")
    html = resp.get_data(as_text=True)

    assert resp.status_code == 200
    assert "לא נמצאו מודעות" in html
    assert 'dir="rtl"' in html


def test_like_wildcards_are_literal(client, db):
    _seed(db)
    login(client, "alice@example.com")

    html = client.get("/listings/search?q=%25").get_data(as_text=True)

    assert "לא נמצאו מודעות" in html


def test_visitor_is_redirected_to_login(client, db):
    resp = client.get("/listings/search")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
