"""F8 – Moderator decision (T-F8-1..6), and the event history of F4 (T-F4-4)."""

import pytest

import app.commands.decide_listing as decide_listing
from app.commands.record_assessment import RecordAssessmentCommand, handle_record_assessment
from app.events.projections import project
from app.events.types import LISTING_APPROVED, LISTING_CREATED, LISTING_EVALUATED, LISTING_REJECTED
from app.models.event import Event
from app.models.listing import (
    STATUS_APPROVED,
    STATUS_EVALUATED,
    STATUS_PENDING_EVALUATION,
    STATUS_REJECTED,
    Listing,
)
from app.models.user import AGENT_EMAIL, AGENT_NAME, ROLE_AGENT, User
from tests.conftest import login, make_user
from tests.test_phase7_mcp_tools import publish

REASON = "המחיר גבוה מאוד ממחיר מוצר חדש."


@pytest.fixture(autouse=True)
def vector_db(monkeypatch):
    """Stands in for Chroma + Ollama; records what approving a listing indexes."""
    indexed = []
    monkeypatch.setattr(decide_listing, "index_listings", lambda documents: indexed.extend(documents))
    return indexed


@pytest.fixture
def people(db):
    alice = make_user(db, "alice@example.com", "seller")
    make_user(db, "bob@example.com", "seller")
    moderator = make_user(db, "mod@example.com", "moderator")
    db.add(User(name=AGENT_NAME, email=AGENT_EMAIL, password_hash="x", role=ROLE_AGENT))
    db.commit()
    return alice, moderator


def evaluated(db, seller, title="אופני הרים"):
    listing_id = publish(db, seller, title=title)
    handle_record_assessment(db, RecordAssessmentCommand(
        listing_id=listing_id, price_vs_market=50, price_vs_market_reason="נמוך ממחיר מוצר חדש.",
        price_vs_similar=25, price_vs_similar_reason="דומה למודעות דומות.",
        listing_quality=15, listing_quality_reason="התיאור קצר.",
        market_price_min=None, market_price_max=None, reasoning="נימוק.",
    ))
    return listing_id


def status_of(db, listing_id):
    db.expire_all()
    return db.get(Listing, listing_id).status


def events_of(db, listing_id):
    db.expire_all()
    return db.query(Event).filter_by(listing_id=listing_id).order_by(Event.id).all()


# --- T-F8-1: approve ------------------------------------------------------------------------


def test_t_f8_1_moderator_approves_an_evaluated_listing(client, db, people, vector_db):
    alice, moderator = people
    listing_id = evaluated(db, alice)
    login(client, "mod@example.com")

    resp = client.post(f"/listings/{listing_id}/approve", follow_redirects=True)

    assert "המודעה אושרה" in resp.get_data(as_text=True)
    assert status_of(db, listing_id) == STATUS_APPROVED
    approved = events_of(db, listing_id)[-1]
    assert (approved.event_type, approved.actor_id) == (LISTING_APPROVED, moderator.id)
    # Another seller finds it in search right away.
    client.post("/logout")
    login(client, "bob@example.com")
    assert "אופני הרים" in client.get("/listings/search").get_data(as_text=True)
    # And the agent can now compare new listings with it.
    assert [(doc.listing_id, doc.source) for doc in vector_db] == [(listing_id, "approved")]


def test_approval_stands_when_the_vector_database_fails(client, db, people, monkeypatch):
    alice, _ = people
    listing_id = evaluated(db, alice)

    def ollama_down(documents):
        raise OSError("Cannot reach Ollama")

    monkeypatch.setattr(decide_listing, "index_listings", ollama_down)
    login(client, "mod@example.com")

    html = client.post(f"/listings/{listing_id}/approve", follow_redirects=True).get_data(as_text=True)

    assert status_of(db, listing_id) == STATUS_APPROVED
    assert "index_approved_listings.py" in html


# --- T-F8-2: reject with a reason -----------------------------------------------------------


def test_t_f8_2_moderator_rejects_with_a_reason_seller_sees_it(client, db, people, vector_db):
    alice, moderator = people
    listing_id = evaluated(db, alice)
    login(client, "mod@example.com")

    client.post(f"/listings/{listing_id}/reject", data={"reason": f"  {REASON}  "})

    assert status_of(db, listing_id) == STATUS_REJECTED
    rejected = events_of(db, listing_id)[-1]
    assert (rejected.event_type, rejected.actor_id, rejected.payload) == (
        LISTING_REJECTED, moderator.id, {"reason": REASON})
    assert vector_db == []  # only approved listings go to the vector database
    client.post("/logout")
    login(client, "alice@example.com")
    html = client.get(f"/listings/{listing_id}").get_data(as_text=True)
    assert REASON in html and "נדחתה" in html


@pytest.mark.parametrize(
    "reason, error",
    [("", "5 תווים לפחות"), ("   ", "5 תווים לפחות"), ("לא", "5 תווים לפחות"), ("x" * 1001, "עד 1000 תווים")],
)
def test_invalid_reason_shows_the_form_again_and_saves_nothing(client, db, people, reason, error):
    alice, _ = people
    listing_id = evaluated(db, alice)
    login(client, "mod@example.com")

    resp = client.post(f"/listings/{listing_id}/reject", data={"reason": reason})

    assert resp.status_code == 400
    assert error in resp.get_data(as_text=True)
    assert status_of(db, listing_id) == STATUS_EVALUATED
    assert events_of(db, listing_id)[-1].event_type == LISTING_EVALUATED


def test_rejection_form_keeps_what_the_moderator_wrote(client, db, people):
    alice, _ = people
    listing_id = evaluated(db, alice)
    login(client, "mod@example.com")

    html = client.post(f"/listings/{listing_id}/reject", data={"reason": "יקר"}).get_data(as_text=True)

    assert ">יקר</textarea>" in html


# --- T-F8-3: no decision before the evaluation ------------------------------------------------


def test_t_f8_3_pending_listing_has_no_buttons_and_direct_post_is_refused(client, db, people):
    alice, _ = people
    listing_id = publish(db, alice)
    login(client, "mod@example.com")

    page = client.get(f"/listings/{listing_id}").get_data(as_text=True)
    resp = client.post(f"/listings/{listing_id}/approve", follow_redirects=True)

    assert "/approve" not in page and "/reject" not in page
    assert "טרם העריך" in resp.get_data(as_text=True)
    assert status_of(db, listing_id) == STATUS_PENDING_EVALUATION


# --- T-F8-4: a decision is final, even with two moderators at once ---------------------------


@pytest.mark.parametrize("second", ["approve", "reject"])
def test_t_f8_4_second_decision_is_refused(client, db, people, second):
    alice, _ = people
    listing_id = evaluated(db, alice)
    login(client, "mod@example.com")
    client.post(f"/listings/{listing_id}/approve")

    resp = client.post(f"/listings/{listing_id}/{second}", data={"reason": REASON}, follow_redirects=True)

    assert "המודעה כבר טופלה" in resp.get_data(as_text=True)
    assert status_of(db, listing_id) == STATUS_APPROVED
    types = [e.event_type for e in events_of(db, listing_id)]
    assert types == [LISTING_CREATED, LISTING_EVALUATED, LISTING_APPROVED]


def test_decided_listing_shows_no_buttons(client, db, people):
    alice, _ = people
    listing_id = evaluated(db, alice)
    login(client, "mod@example.com")
    client.post(f"/listings/{listing_id}/approve")

    assert "/reject" not in client.get(f"/listings/{listing_id}").get_data(as_text=True)


# --- T-F8-5: only a moderator decides --------------------------------------------------------


def test_t_f8_5_seller_sees_no_buttons_and_cannot_decide(client, db, people):
    alice, _ = people
    listing_id = evaluated(db, alice)
    login(client, "alice@example.com")

    page = client.get(f"/listings/{listing_id}").get_data(as_text=True)
    approve = client.post(f"/listings/{listing_id}/approve")
    reject = client.post(f"/listings/{listing_id}/reject", data={"reason": REASON})

    assert "/approve" not in page
    assert approve.status_code == reject.status_code == 302  # sent back to the home page
    assert status_of(db, listing_id) == STATUS_EVALUATED


def test_visitor_is_sent_to_login(client, db, people):
    alice, _ = people
    listing_id = evaluated(db, alice)

    resp = client.post(f"/listings/{listing_id}/approve")

    assert "/login" in resp.headers["Location"]
    assert status_of(db, listing_id) == STATUS_EVALUATED


def test_buttons_ask_for_confirmation(client, db, people):
    alice, _ = people
    listing_id = evaluated(db, alice)
    login(client, "mod@example.com")

    html = client.get(f"/listings/{listing_id}").get_data(as_text=True)

    assert "confirm('לאשר את המודעה?')" in html and "confirm('לדחות את המודעה?')" in html


# --- T-F4-4: the moderator sees the event history ---------------------------------------------


def test_t_f4_4_moderator_sees_the_event_history(client, db, people):
    alice, _ = people
    listing_id = evaluated(db, alice)
    login(client, "mod@example.com")
    client.post(f"/listings/{listing_id}/reject", data={"reason": REASON})

    html = client.get(f"/listings/{listing_id}").get_data(as_text=True)

    history = html[html.index("היסטוריית המודעה"):]
    for text in ["נוצרה", "alice (מוכר/ת)", "הוערכה", f"{AGENT_NAME} (סוכן)", "נדחתה", "mod (מנהל/ת תוכן)", REASON]:
        assert text in history
    assert history.index("נוצרה") < history.index("הוערכה") < history.index("נדחתה")


def test_seller_never_sees_the_history(client, db, people):
    alice, _ = people
    listing_id = evaluated(db, alice)
    login(client, "alice@example.com")

    html = client.get(f"/listings/{listing_id}").get_data(as_text=True)

    assert "היסטוריית המודעה" not in html and "mod (" not in html


# --- T-F8-6: the read model can be rebuilt from the decision events --------------------------


def test_t_f8_6_decisions_replay_from_events(client, db, people):
    alice, _ = people
    approved, rejected = evaluated(db, alice, "ראשונה"), evaluated(db, alice, "שנייה")
    login(client, "mod@example.com")
    client.post(f"/listings/{approved}/approve")
    client.post(f"/listings/{rejected}/reject", data={"reason": REASON})

    def snapshot():
        db.expire_all()
        return [(l.id, l.status, l.rejection_reason) for l in db.query(Listing).order_by(Listing.id)]

    before = snapshot()
    from app.models.assessment import Assessment

    db.query(Assessment).delete()
    db.query(Listing).delete()
    db.commit()
    for event in db.query(Event).order_by(Event.id):
        project(db, event)
        db.flush()
    db.commit()

    assert snapshot() == before
    assert {status for _, status, _ in before} == {STATUS_APPROVED, STATUS_REJECTED}


def test_catch_up_script_takes_only_approved_listings(client, db, people):
    from scripts.index_approved_listings import approved_documents

    alice, _ = people
    approved, _still_evaluated = evaluated(db, alice, "ראשונה"), evaluated(db, alice, "שנייה")
    login(client, "mod@example.com")
    client.post(f"/listings/{approved}/approve")

    assert [doc.listing_id for doc in approved_documents(db)] == [approved]


def test_t_f8_5_agent_account_can_never_decide(db, people):
    # .claude/rules/agent-never-decides.md: the agent only gives an opinion.
    alice, _ = people
    listing_id = evaluated(db, alice)
    agent = db.query(User).filter_by(email=AGENT_EMAIL).one()

    with pytest.raises(decide_listing.DecideListingError):
        decide_listing.handle_approve_listing(db, decide_listing.ApproveListingCommand(agent.id, listing_id))
    db.rollback()
    with pytest.raises(decide_listing.DecideListingError):
        decide_listing.handle_reject_listing(db, decide_listing.RejectListingCommand(agent.id, listing_id, REASON))
    db.rollback()

    assert status_of(db, listing_id) == STATUS_EVALUATED
