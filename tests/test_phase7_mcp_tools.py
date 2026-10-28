"""Phase 7 – our own MCP tools: get pending listing, save assessment (T-MCP-1..7, T-ARCH-6)."""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from mcp.server.fastmcp.exceptions import ToolError
from mcp.shared.memory import create_connected_server_and_client_session

from app.commands.publish_listing import PublishListingCommand, handle_publish_listing
from app.commands.record_assessment import confidence_for, recommendation_for
from app.events.projections import project
from app.events.types import LISTING_CREATED, LISTING_EVALUATED
from app.mcp_tools import server
from app.models.assessment import Assessment
from app.models.event import Event
from app.models.listing import STATUS_APPROVED, STATUS_EVALUATED, STATUS_PENDING_EVALUATION, Listing
from app.models.user import AGENT_EMAIL, AGENT_NAME, ROLE_AGENT, User
from tests.conftest import login, make_listing, make_user


@pytest.fixture(autouse=True)
def tools(app):
    server.configure(app.engine)
    yield
    server._session_factory = None


@pytest.fixture
def agent(db):
    user = User(name=AGENT_NAME, email=AGENT_EMAIL, password_hash="x", role=ROLE_AGENT)
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def seller(db):
    make_user(db, "mod@example.com", "moderator")
    return make_user(db, "alice@example.com", "seller")


def publish(db, seller, title="אופני הרים", price="450"):
    return handle_publish_listing(
        db,
        PublishListingCommand(
            seller_id=seller.id, title=title, description="אופניים במצב טוב, 21 הילוכים",
            price=price, category="sports",
        ),
    )


def call(name, **arguments):
    """Call a tool through FastMCP (argument validation included); returns the JSON result."""
    _content, structured = asyncio.run(server.mcp.call_tool(name, arguments))
    return unwrap(structured)


def unwrap(structured):
    # FastMCP wraps an optional result as {"result": ...}; a plain TypedDict is returned as is.
    return structured["result"] if set(structured) == {"result"} else structured


def assessment_args(listing_id, **overrides):
    args = {
        "listing_id": listing_id,
        "price_vs_market": 40,
        "price_vs_market_reason": "המחיר מעט מתחת לטווח השוק",
        "price_vs_similar": 20,
        "price_vs_similar_reason": "דומה למודעות דומות",
        "listing_quality": 20,
        "listing_quality_reason": "תיאור מפורט וקטגוריה נכונה",
        "market_price_min": 400,
        "market_price_max": 700,
        "market_price_new": 550,
        "similar_listing_ids": ["sample-01", "sample-02", "sample-03"],
        "reasoning": "מחיר הוגן ותיאור אמין.",
    }
    args.update(overrides)
    return args


def events_of(db, listing_id):
    db.expire_all()
    return db.query(Event).filter_by(listing_id=listing_id).order_by(Event.id).all()


# --- T-MCP-1: get_pending_listing ---------------------------------------------------------


def test_t_mcp_1_get_pending_listing_returns_oldest_pending_first(db, seller):
    now = datetime.now(timezone.utc)
    make_listing(db, seller, "חדשה", STATUS_PENDING_EVALUATION, created_at=now)
    oldest = make_listing(db, seller, "ישנה", STATUS_PENDING_EVALUATION, created_at=now - timedelta(hours=2),
                          price="450", category="sports", description="תיאור")
    make_listing(db, seller, "מאושרת", STATUS_APPROVED, created_at=now - timedelta(days=1))

    result = call("get_pending_listing")

    assert result == {
        "id": oldest.id,
        "title": "ישנה",
        "description": "תיאור",
        "price": 450.0,
        "category": "sports",
        "created_at": result["created_at"],
    }
    assert "seller" not in str(result.keys())


def test_t_mcp_1_get_pending_listing_skips_excluded_ids(db, seller):
    now = datetime.now(timezone.utc)
    first = make_listing(db, seller, "ראשונה", STATUS_PENDING_EVALUATION, created_at=now - timedelta(hours=1))
    second = make_listing(db, seller, "שנייה", STATUS_PENDING_EVALUATION, created_at=now)

    assert call("get_pending_listing", exclude_ids=[first.id])["id"] == second.id
    assert call("get_pending_listing", exclude_ids=[first.id, second.id]) is None


def test_t_mcp_1_get_pending_listing_returns_null_when_queue_is_empty(db, seller):
    make_listing(db, seller, "מאושרת", STATUS_APPROVED)

    assert call("get_pending_listing") is None


def test_t_mcp_1_get_pending_listing_locks_and_writes_nothing(db, seller):
    listing_id = publish(db, seller)

    call("get_pending_listing")
    call("get_pending_listing")

    assert [e.event_type for e in events_of(db, listing_id)] == [LISTING_CREATED]
    assert db.get(Listing, listing_id).status == STATUS_PENDING_EVALUATION


# --- T-MCP-2: save_assessment --------------------------------------------------------------


def test_t_mcp_2_save_assessment_records_event_and_read_model(db, seller, agent):
    listing_id = publish(db, seller)

    result = call("save_assessment", **assessment_args(listing_id))

    assert result == {
        "listing_id": listing_id,
        "score": 80,
        "recommendation": "approve",
        "confidence": "high",
        "status": STATUS_EVALUATED,
    }
    events = events_of(db, listing_id)
    assert [e.event_type for e in events] == [LISTING_CREATED, LISTING_EVALUATED]
    evaluated = events[1]
    assert evaluated.actor_id == agent.id
    # Computed values are stored in the event, so a replay never recomputes them.
    assert evaluated.payload["score"] == 80
    assert evaluated.payload["recommendation"] == "approve"
    assert evaluated.payload["confidence"] == "high"

    assert db.get(Listing, listing_id).status == STATUS_EVALUATED
    stored = db.get(Assessment, listing_id)
    assert stored.score == 80
    assert (stored.price_vs_market, stored.price_vs_similar, stored.listing_quality) == (40, 20, 20)
    assert stored.market_price_min == Decimal("400.00")
    assert stored.market_price_max == Decimal("700.00")
    assert stored.market_price_new == Decimal("550.00")
    assert stored.similar_listing_ids == ["sample-01", "sample-02", "sample-03"]
    assert stored.reasoning == "מחיר הוגן ותיאור אמין."
    assert stored.evaluated_at is not None


def test_t_mcp_2_save_assessment_cleans_similar_ids(db, seller, agent):
    listing_id = publish(db, seller)

    call("save_assessment", **assessment_args(
        listing_id, similar_listing_ids=[" sample-01 ", listing_id, "sample-01", ""],
    ))

    assert db.get(Assessment, listing_id).similar_listing_ids == ["sample-01"]


def test_t_mcp_2_save_assessment_accepts_no_similar_listings(db, seller, agent):
    listing_id = publish(db, seller)

    result = call("save_assessment", **assessment_args(listing_id, similar_listing_ids=[]))

    assert result["confidence"] == "low"


@pytest.mark.parametrize(
    "score, expected",
    [(100, "approve"), (70, "approve"), (69, "manual_review"), (40, "manual_review"), (39, "reject"), (0, "reject")],
)
def test_t_mcp_2_recommendation_thresholds(score, expected):
    assert recommendation_for(score) == expected


@pytest.mark.parametrize(
    "similar, low, high, expected",
    [
        (0, "400", "500", "low"),
        (3, None, None, "low"),  # no price found on the web
        (1, "400", "500", "medium"),
        (2, "400", "500", "medium"),
        (3, "400", "800", "high"),  # max exactly twice min is still a tight range
        (3, "400", "801", "medium"),
        (5, "400", "2000", "medium"),
    ],
)
def test_t_mcp_2_confidence_rule(similar, low, high, expected):
    to_decimal = lambda value: None if value is None else Decimal(value)  # noqa: E731
    assert confidence_for(similar, to_decimal(low), to_decimal(high)) == expected


# --- T-MCP-3: invalid input saves nothing ---------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"price_vs_market": 51},
        {"price_vs_market": -1},
        {"price_vs_similar": 26},
        {"listing_quality": 26},
        {"price_vs_market_reason": "   "},
        {"listing_quality_reason": ""},
        {"reasoning": ""},
        {"market_price_min": 0},
        {"market_price_min": -10},
        {"market_price_min": 800, "market_price_max": 700},
        {"market_price_new": 800},  # outside the range
        {"market_price_new": None},  # the range without the new price
        {"market_price_min": None},
        {"listing_id": "does-not-exist"},
    ],
    ids=lambda overrides: ",".join(overrides),
)
def test_t_mcp_3_invalid_assessment_is_refused_and_nothing_saved(db, seller, agent, overrides):
    listing_id = publish(db, seller)

    with pytest.raises(ToolError):
        call("save_assessment", **{**assessment_args(listing_id), **overrides})

    assert [e.event_type for e in events_of(db, listing_id)] == [LISTING_CREATED]
    assert db.get(Listing, listing_id).status == STATUS_PENDING_EVALUATION
    assert db.query(Assessment).count() == 0


def test_t_mcp_2_no_price_found_on_the_web_is_saved_with_low_confidence(db, seller, agent):
    listing_id = publish(db, seller)

    result = call("save_assessment", **assessment_args(
        listing_id, market_price_min=None, market_price_max=None, market_price_new=None))

    assert result["confidence"] == "low"
    stored = db.get(Assessment, listing_id)
    assert (stored.market_price_min, stored.market_price_max, stored.market_price_new) == (None, None, None)
    assert events_of(db, listing_id)[1].payload["market_price_new"] is None


def test_t_mcp_3_missing_agent_account_is_refused(db, seller):
    listing_id = publish(db, seller)

    with pytest.raises(ToolError, match="create_agent_user"):
        call("save_assessment", **assessment_args(listing_id))

    assert db.get(Listing, listing_id).status == STATUS_PENDING_EVALUATION


def test_t_mcp_3_seller_with_agent_email_is_not_the_agent(db, seller):
    make_user(db, AGENT_EMAIL, "seller")
    listing_id = publish(db, seller)

    with pytest.raises(ToolError, match="create_agent_user"):
        call("save_assessment", **assessment_args(listing_id))


# --- T-MCP-4: a listing is evaluated once ---------------------------------------------------


def test_t_mcp_4_listing_is_evaluated_only_once(db, seller, agent):
    listing_id = publish(db, seller)
    call("save_assessment", **assessment_args(listing_id))

    with pytest.raises(ToolError, match="not Pending evaluation"):
        call("save_assessment", **assessment_args(listing_id, price_vs_market=0))

    assert [e.event_type for e in events_of(db, listing_id)] == [LISTING_CREATED, LISTING_EVALUATED]
    assert db.get(Assessment, listing_id).score == 80
    assert call("get_pending_listing") is None


def test_t_mcp_4_approved_listing_cannot_be_evaluated(db, seller, agent):
    listing = make_listing(db, seller, "מאושרת", STATUS_APPROVED)

    with pytest.raises(ToolError, match="not Pending evaluation"):
        call("save_assessment", **assessment_args(listing.id))


# --- T-MCP-5: the agent account cannot log in -----------------------------------------------


def test_t_mcp_5_agent_account_cannot_log_in(client, db):
    from werkzeug.security import generate_password_hash

    db.add(User(name=AGENT_NAME, email=AGENT_EMAIL,
                password_hash=generate_password_hash("password123"), role=ROLE_AGENT))
    db.commit()

    resp = client.post("/login", data={"email": AGENT_EMAIL, "password": "password123"})

    assert resp.status_code == 401
    assert client.get("/listings").status_code == 302


# --- T-MCP-6: the assessment is visible to the moderator only --------------------------------


def test_t_mcp_6_moderator_sees_saved_assessment(client, db, seller, agent):
    listing_id = publish(db, seller)
    call("save_assessment", **assessment_args(listing_id))
    login(client, "mod@example.com")

    details = client.get(f"/listings/{listing_id}").get_data(as_text=True)
    table = client.get("/listings").get_data(as_text=True)
    search = client.get("/listings/search").get_data(as_text=True)

    for text in ["80", "40 / 50", "20 / 25", "לאשר", "גבוהה", "400.00", "700.00", "550.00",
                 "מחיר הוגן ותיאור אמין.", "המחיר מעט מתחת לטווח השוק"]:
        assert text in details
    # The similar listing ids are kept in the assessment but not shown: they are not titles.
    assert "sample-01" not in details
    assert "טרם הוערכה" not in details
    assert ">80<" in table
    assert "ציון הסוכן: 80" in search


def test_moderator_sees_when_no_price_was_found(client, db, seller, agent):
    listing_id = publish(db, seller)
    call("save_assessment", **assessment_args(
        listing_id, market_price_min=None, market_price_max=None, market_price_new=None))
    login(client, "mod@example.com")

    details = client.get(f"/listings/{listing_id}").get_data(as_text=True)

    assert "טווח מחירי שוק</dt>\n          <dd>לא נמצאו" in details


def test_t_mcp_6_seller_never_sees_saved_assessment(client, db, seller, agent):
    listing_id = publish(db, seller)
    call("save_assessment", **assessment_args(listing_id))
    login(client, "alice@example.com")

    details = client.get(f"/listings/{listing_id}").get_data(as_text=True)
    table = client.get("/listings").get_data(as_text=True)

    assert "הערכת הסוכן" not in details
    assert "מחיר הוגן ותיאור אמין." not in details
    assert "ציון הסוכן" not in table


def test_moderator_table_sorts_by_score_with_unevaluated_last(client, db, seller, agent):
    low = publish(db, seller, title="זולה")
    high = publish(db, seller, title="יקרה")
    publish(db, seller, title="שולחן עץ")  # not evaluated yet
    call("save_assessment", **assessment_args(low, price_vs_market=0))
    call("save_assessment", **assessment_args(high))
    login(client, "mod@example.com")

    for direction in ("desc", "asc"):
        html = client.get(f"/listings?sort=score&dir={direction}").get_data(as_text=True)
        order = [html.index("יקרה"), html.index("זולה")]
        assert order == sorted(order) if direction == "desc" else order == sorted(order, reverse=True)
        assert html.index("שולחן עץ") > max(order)


# --- T-MCP-7: through the real MCP protocol --------------------------------------------------


def test_t_mcp_7_tools_work_through_an_mcp_client(db, seller, agent):
    listing_id = publish(db, seller)

    async def scenario():
        async with create_connected_server_and_client_session(server.mcp) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            pending = await client.call_tool("get_pending_listing", {})
            bad = await client.call_tool("save_assessment", assessment_args(listing_id, price_vs_market=99))
            good = await client.call_tool("save_assessment", assessment_args(listing_id))
            return tools, pending, bad, good

    tools, pending, bad, good = asyncio.run(scenario())

    assert set(tools) == {"get_pending_listing", "save_assessment"}
    assert set(tools["save_assessment"].inputSchema["required"]) == set(assessment_args("x")) - {"market_price_new"}
    assert unwrap(pending.structuredContent)["id"] == listing_id
    assert bad.isError and "price_vs_market" in bad.content[0].text
    assert not good.isError and unwrap(good.structuredContent)["score"] == 80


# --- T-ARCH-6: the read model can be rebuilt from the events ---------------------------------


def test_t_arch_6_read_model_rebuilt_from_events_includes_assessments(db, seller, agent):
    evaluated_id = publish(db, seller, title="הוערכה")
    publish(db, seller, title="ממתינה")
    call("save_assessment", **assessment_args(evaluated_id))

    def snapshot():
        db.expire_all()
        listings = [(l.id, l.status, l.title, l.price) for l in db.query(Listing).order_by(Listing.id)]
        assessments = [
            (a.listing_id, a.score, a.recommendation, a.confidence, a.market_price_min,
             a.market_price_max, a.market_price_new, a.similar_listing_ids, a.reasoning,
             a.price_vs_market_reason)
            for a in db.query(Assessment).order_by(Assessment.listing_id)
        ]
        return listings, assessments

    before = snapshot()
    db.query(Assessment).delete()
    db.query(Listing).delete()
    db.commit()

    for event in db.query(Event).order_by(Event.id):
        project(db, event)
        db.flush()
    db.commit()

    assert snapshot() == before


# --- Errors the agent can act on ------------------------------------------------------------


def test_tool_schema_shows_sub_score_ranges():
    schema = server.mcp._tool_manager.get_tool("save_assessment").parameters["properties"]

    assert (schema["price_vs_market"]["minimum"], schema["price_vs_market"]["maximum"]) == (0, 50)
    assert schema["price_vs_similar"]["maximum"] == 25
    assert schema["listing_quality"]["maximum"] == 25
    assert schema["reasoning"]["description"]


def test_database_error_gives_a_short_message_and_saves_nothing(db, seller, agent, monkeypatch):
    from sqlalchemy.exc import OperationalError

    listing_id = publish(db, seller)

    def broken(*_args, **_kwargs):
        raise OperationalError("SELECT secret FROM users", {}, Exception("host db.neon.tech refused"))

    monkeypatch.setattr(server, "handle_record_assessment", broken)

    with pytest.raises(ToolError, match="database is unreachable") as error:
        call("save_assessment", **assessment_args(listing_id))

    assert "SELECT" not in str(error.value) and "neon" not in str(error.value)
    assert db.get(Listing, listing_id).status == STATUS_PENDING_EVALUATION


def test_unreachable_database_at_first_connection_gives_the_short_message(monkeypatch):
    # Seen offline: the first connection (create_all) failed outside the session guard
    # and the raw driver error, with the Neon host name, reached the agent.
    from sqlalchemy.exc import OperationalError

    def unreachable():
        raise OperationalError("connect", {}, Exception("failed to resolve host ep-x.neon.tech"))

    server._session_factory = None
    monkeypatch.setattr(server, "_default_engine", unreachable)

    with pytest.raises(ToolError, match="database is unreachable") as error:
        call("get_pending_listing")

    assert "neon" not in str(error.value)
