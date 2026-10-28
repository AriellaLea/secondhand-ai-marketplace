"""F7 – the AI agent process, with a scripted fake LLM and a fake Tavily (T-AGENT-1, 2, 3, 5, 6, 7).

Our MCP server is the real one, reached through the real MCP protocol in memory.
T-AGENT-3 is also checked by hand; T-AGENT-4 and 8 need the real model and Tavily.
"""

import asyncio
from contextlib import asynccontextmanager

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool, ToolException
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.shared.memory import create_connected_server_and_client_session

import agent.__main__ as agent_main
from decimal import Decimal

from agent.tools import prices_in_text, query_mentions_title
from app.events.types import LISTING_CREATED, LISTING_EVALUATED
from app.mcp_tools import server
from app.models.assessment import Assessment
from app.models.event import Event
from app.models.listing import STATUS_EVALUATED, STATUS_PENDING_EVALUATION, Listing
from app.models.user import AGENT_EMAIL, AGENT_NAME, ROLE_AGENT, User
from app.pricing import MARKET_NO_PRICE, MARKET_NO_PRICE_REASON, NO_SIMILAR_REASON, NO_SIMILAR_SCORE
from app.vector_store import SimilarListing
from tests.test_phase7_mcp_tools import publish

# The new-item prices the model reads: 1,290, 2490 and 3.200 ILS (median 2490).
WEB_RESULTS = (
    "Detailed Results:\n\nTitle: אופני הרים חדשים\nURL: https://example.co.il/bike\n"
    "Content: אופני הרים 27.5 במחיר 1,290 ₪, דגם מתקדם 2490 ש\"ח, דגם מקצועי 3.200 ₪"
)


@pytest.fixture(autouse=True)
def tools(app):
    server.configure(app.engine)
    yield
    server._session_factory = None


@pytest.fixture
def agent_account(db):
    db.add(User(name=AGENT_NAME, email=AGENT_EMAIL, password_hash="x", role=ROLE_AGENT))
    db.commit()


@pytest.fixture
def seller(db):
    from tests.conftest import make_user

    return make_user(db, "alice@example.com", "seller")


BOUND_TOOLS: list[str] = []  # names of the tools the agent offered to the model


class ScriptedModel(GenericFakeChatModel):
    """Replays AI messages in order; tools are recorded and ignored."""

    def bind_tools(self, tools, **kwargs):
        BOUND_TOOLS[:] = [tool.name for tool in tools]
        return self


def call(name, args=None, call_id="1"):
    return {"name": name, "args": args or {}, "id": call_id, "type": "tool_call"}


def save_args(**overrides):
    args = {"web_prices": [1290, 2490, 3200], "description_matches_title": True}
    args.update(overrides)
    return args


def happy_path():
    """The messages a well-behaved model sends for one listing."""
    return [
        AIMessage(content="", tool_calls=[call("search_similar_listings", call_id="a")]),
        AIMessage(content="", tool_calls=[call("tavily_search", {"query": "אופני הרים מחיר"}, "b")]),
        AIMessage(content="", tool_calls=[call("save_assessment", save_args(), "c")]),
        AIMessage(content="Done."),
    ]


SIMILAR_CALLS: list[dict] = []  # the arguments of each similar-listing search


def fake_similar(title, description, k=5, exclude_id=None, category=None):
    SIMILAR_CALLS.append({"title": title, "category": category})
    return [
        SimilarListing("sample-13", "אופני הרים 27.5 אינץ'", "sports", 900.0, 0.63),
        SimilarListing("sample-10", "כיסא משרדי", "furniture", 450.0, 0.53),  # below the threshold
    ]


class FakeTavily:
    """Stands in for the Tavily MCP tool; records the queries it receives."""

    def __init__(self, result=WEB_RESULTS, error=None):
        self.result, self.error, self.calls = result, error, []

    def tool(self):
        async def tavily_search(**kwargs):
            self.calls.append(kwargs)
            if self.error:
                raise ToolException(self.error)
            return [{"type": "text", "text": self.result}], None  # (content, artifact) like MCP tools

        return StructuredTool.from_function(
            coroutine=tavily_search, name="tavily_search", description="web search",
            args_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            response_format="content_and_artifact",
        )


def run_agent(messages, tavily=None, similar=fake_similar):
    tavily = tavily or FakeTavily()

    @asynccontextmanager
    async def open_tools():
        async with create_connected_server_and_client_session(server.mcp) as session:
            tools = {t.name: t for t in await load_mcp_tools(session, handle_tool_errors=False)}
            tools["tavily_search"] = tavily.tool()
            yield tools

    model = ScriptedModel(messages=iter(messages))
    asyncio.run(agent_main.run_agent(once=True, open_tools=open_tools,
                                     make_model=lambda: model, similar=similar))
    return tavily


def events_of(db, listing_id):
    db.expire_all()
    return [e.event_type for e in db.query(Event).filter_by(listing_id=listing_id).order_by(Event.id)]


# --- T-AGENT-1, 2: the agent evaluates a pending listing on its own ----------------------------


def test_t_agent_2_agent_evaluates_pending_listing(db, seller, agent_account):
    listing_id = publish(db, seller)

    tavily = run_agent(happy_path())

    assert db.get(Listing, listing_id).status == STATUS_EVALUATED
    stored = db.get(Assessment, listing_id)
    # 450 ILS: below the new price (median 2490) and the similar listing (900); 5-word description.
    assert (stored.price_vs_market, stored.price_vs_similar, stored.listing_quality) == (50, 25, 15)
    assert (stored.score, stored.recommendation, stored.confidence) == (90, "approve", "medium")
    assert stored.listing_quality_reason == "התיאור קצר ומתאים לפריט שבכותרת."
    assert (stored.market_price_min, stored.market_price_new, stored.market_price_max) == (1290, 2490, 3200)
    assert stored.price_vs_market_reason == "מחיר המודעה (450 ₪) נמוך ממחיר מוצר חדש באינטרנט (2,490 ₪)."
    assert stored.reasoning == (
        "מחיר המודעה (450 ₪) נמוך ממחיר מוצר חדש באינטרנט (2,490 ₪). "
        "מחיר המודעה (450 ₪) דומה למחירי המודעות הדומות או נמוך מהם (900 ₪). "
        "התיאור קצר ומתאים לפריט שבכותרת. ההמלצה: לאשר."
    )
    # The program fills in the ids the similar-listing search returned above the threshold.
    assert stored.similar_listing_ids == ["sample-13"]
    assert tavily.calls[0]["query"] == "אופני הרים מחיר"


# --- T-AGENT-3: a fair listing scores higher than an overpriced one ---------------------------


def test_t_agent_3_fair_listing_scores_higher_than_overpriced(db, seller, agent_account):
    fair = publish(db, seller, price="800")
    overpriced = publish(db, seller, price="6000")

    run_agent(happy_path() + happy_path())

    fair_assessment, overpriced_assessment = db.get(Assessment, fair), db.get(Assessment, overpriced)
    assert fair_assessment.score > overpriced_assessment.score
    assert (overpriced_assessment.price_vs_market, overpriced_assessment.recommendation) == (0, "reject")
    assert "גבוה ממחיר מוצר חדש" in overpriced_assessment.reasoning


# --- T-AGENT-7: the agent never approves or rejects ------------------------------------------


def test_t_agent_7_only_new_event_is_listing_evaluated(db, seller, agent_account):
    listing_id = publish(db, seller)

    run_agent(happy_path())

    assert events_of(db, listing_id) == [LISTING_CREATED, LISTING_EVALUATED]


# --- T-AGENT-5: web search fails -> nothing saved ---------------------------------------------


@pytest.mark.parametrize(
    "tavily",
    [
        lambda: FakeTavily(error="network down"),
        lambda: FakeTavily(result='Tavily API error: {"error":"Unauthorized: missing or invalid API key."}'),
        lambda: FakeTavily(result="Detailed Results:\n"),  # no result at all
    ],
    ids=["tool-error", "api-error-as-text", "no-results"],
)
def test_t_agent_5_failed_web_search_saves_nothing(db, seller, agent_account, tavily):
    listing_id = publish(db, seller)

    # Even if the model ignores the failure and tries to save, the program refuses.
    run_agent(happy_path(), tavily=tavily())

    assert db.get(Listing, listing_id).status == STATUS_PENDING_EVALUATION
    assert db.query(Assessment).count() == 0
    assert events_of(db, listing_id) == [LISTING_CREATED]


def test_save_refused_without_similar_listing_search(db, seller, agent_account):
    listing_id = publish(db, seller)
    messages = [
        AIMessage(content="", tool_calls=[call("tavily_search", {"query": "אופני הרים"}, "b")]),
        AIMessage(content="", tool_calls=[call("save_assessment", save_args(), "c")]),
        AIMessage(content="Done."),
    ]

    run_agent(messages)

    assert db.get(Listing, listing_id).status == STATUS_PENDING_EVALUATION


def test_model_that_stops_without_saving_leaves_listing_pending(db, seller, agent_account):
    listing_id = publish(db, seller)

    run_agent([AIMessage(content="I cannot evaluate this listing.")])

    assert db.get(Listing, listing_id).status == STATUS_PENDING_EVALUATION


def test_web_search_limit(db, seller, agent_account):
    publish(db, seller)
    messages = [
        AIMessage(content="", tool_calls=[call("tavily_search", {"query": f"אופני הרים {n}"}, f"s{n}")])
        for n in range(3)
    ] + [AIMessage(content="Done.")]

    tavily = run_agent(messages)

    assert len(tavily.calls) == 2


def test_invalid_values_can_be_fixed_by_the_model(db, seller, agent_account):
    listing_id = publish(db, seller)
    messages = happy_path()
    messages.insert(2, AIMessage(content="", tool_calls=[call("save_assessment", save_args(description_matches_title="maybe"), "x")]))

    run_agent(messages)

    assert db.get(Assessment, listing_id).listing_quality == 15


def test_missing_agent_account_stops_the_process(db, seller):
    listing_id = publish(db, seller)

    with pytest.raises(agent_main.FatalAgentError, match="create_agent_user"):
        run_agent(happy_path())

    assert db.get(Listing, listing_id).status == STATUS_PENDING_EVALUATION


# --- The model judges the listing quality; the program writes the reason ---------------------


@pytest.mark.parametrize("matches, points", [(True, 15), (False, 5), ("true", 15), ("False", 5)])
def test_listing_quality_from_the_models_answer(db, seller, agent_account, matches, points):
    listing_id = publish(db, seller)  # a 5-word description: short
    messages = happy_path()
    messages[2] = AIMessage(content="", tool_calls=[call(
        "save_assessment", save_args(description_matches_title=matches), "c")])

    run_agent(messages)

    assert db.get(Assessment, listing_id).listing_quality == points


def test_model_never_sees_the_listing_price():
    from agent.prompt import listing_message

    message = listing_message({"id": "x", "title": "אופני הרים", "description": "תיאור", "price": 6000.0,
                               "category": "sports"})

    assert "6000" not in message and "price" not in message


# --- T-AGENT-6: listings published while the agent is stopped are all evaluated -------------


def test_t_agent_6_pending_listings_evaluated_oldest_first(db, seller, agent_account):
    first = publish(db, seller, title="אופני הרים ראשונה")
    second = publish(db, seller, title="אופני הרים שנייה")

    run_agent(happy_path() + happy_path())

    assert db.get(Listing, first).status == STATUS_EVALUATED
    assert db.get(Listing, second).status == STATUS_EVALUATED
    db.expire_all()
    evaluated = db.query(Event).filter_by(event_type=LISTING_EVALUATED).order_by(Event.id).all()
    assert [e.listing_id for e in evaluated] == [first, second]


def test_unreadable_database_is_not_reported_as_an_empty_queue(db, seller, agent_account, caplog, monkeypatch):
    from mcp.server.fastmcp.exceptions import ToolError

    def unreachable(*_args, **_kwargs):
        raise ToolError(server.DATABASE_ERROR)

    monkeypatch.setattr(server, "handle_get_pending_listing", unreachable)

    run_agent([])

    assert "Could not read the pending listings" in caplog.text
    assert "No more pending listings" not in caplog.text


def test_failed_listing_does_not_block_the_next_one(db, seller, agent_account):
    first = publish(db, seller, title="אופני הרים ראשונה")
    second = publish(db, seller, title="אופני הרים שנייה")

    run_agent([AIMessage(content="I give up.")] + happy_path())

    assert db.get(Listing, first).status == STATUS_PENDING_EVALUATION
    assert db.get(Listing, second).status == STATUS_EVALUATED


# --- Startup checks ----------------------------------------------------------------------------


def test_startup_reports_missing_tavily_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    assert any("TAVILY_API_KEY" in problem for problem in agent_main.startup_problems())


# --- Fixes after the first run with the real model ---------------------------------------------


def test_missing_field_gets_a_short_hint_then_is_fixed(db, seller, agent_account, caplog):
    listing_id = publish(db, seller)
    incomplete = {k: v for k, v in save_args().items() if k != "web_prices"}
    messages = happy_path()
    messages.insert(2, AIMessage(content="", tool_calls=[call("save_assessment", incomplete, "x")]))

    run_agent(messages)

    assert "Not saved: add web_prices." in caplog.text
    assert db.get(Assessment, listing_id).market_price_new == 2490


def test_no_similar_listing_the_program_sets_price_vs_similar(db, seller, agent_account):
    listing_id = publish(db, seller)
    run_agent(happy_path(), similar=lambda *args, **kwargs: [])

    assessment = db.get(Assessment, listing_id)
    assert assessment.price_vs_similar == NO_SIMILAR_SCORE
    assert assessment.price_vs_similar_reason == NO_SIMILAR_REASON


def test_save_with_other_tools_is_refused_with_a_reason_then_retried(db, seller, agent_account, caplog):
    caplog.set_level("INFO", logger="agent")
    listing_id = publish(db, seller)
    messages = [
        AIMessage(content="", tool_calls=[
            call("search_similar_listings", call_id="a"), call("tavily_search", {"query": "אופני הרים מחיר"}, "b"),
            call("save_assessment", save_args(description_matches_title=False), "c"),  # written before reading results
        ]),
        AIMessage(content="", tool_calls=[call("save_assessment", save_args(), "d")]),
        AIMessage(content="Done."),
    ]

    run_agent(messages)

    assert "before reading the results of the other tools" in caplog.text
    assert db.get(Assessment, listing_id).listing_quality == 15


def test_model_that_stops_before_saving_is_reminded_once(db, seller, agent_account, caplog):
    caplog.set_level("INFO", logger="agent")
    listing_id = publish(db, seller)
    messages = happy_path()[:2] + [AIMessage(content="Done.")] + happy_path()[2:]

    run_agent(messages)

    assert "reminded to call save_assessment" in caplog.text
    assert db.get(Listing, listing_id).status == STATUS_EVALUATED


def test_reminder_is_sent_only_once(db, seller, agent_account):
    listing_id = publish(db, seller)
    messages = happy_path()[:2] + [AIMessage(content="Done."), AIMessage(content="Done again.")] + happy_path()[2:]

    run_agent(messages)

    assert db.get(Listing, listing_id).status == STATUS_PENDING_EVALUATION


def test_no_reminder_when_the_web_search_failed(db, seller, agent_account, caplog):
    caplog.set_level("INFO", logger="agent")
    publish(db, seller)

    run_agent(happy_path()[:2] + [AIMessage(content="Done.")], tavily=FakeTavily(error="network down"))

    assert "reminded" not in caplog.text


def test_agent_does_not_offer_write_todos(db, seller, agent_account):
    # The file tools are hidden by the "openai" harness profile, which this fake model does not use.
    publish(db, seller)

    run_agent(happy_path())

    assert {"save_assessment", "search_similar_listings", "tavily_search"} <= set(BOUND_TOOLS)
    assert "write_todos" not in BOUND_TOOLS


# --- Fix K: the program checks the web prices and scores the price -----------------------------


def test_prices_not_in_the_web_results_are_ignored(db, seller, agent_account, caplog):
    caplog.set_level("INFO", logger="agent")
    listing_id = publish(db, seller)
    messages = happy_path()
    # 900 is the similar listing's price, 10000 a guess: neither is in the web results.
    messages[2] = AIMessage(content="", tool_calls=[call("save_assessment", save_args(web_prices=[900, 2490, 10000]), "c")])

    run_agent(messages)

    assert "ignored: 900, 10000" in caplog.text
    stored = db.get(Assessment, listing_id)
    assert (stored.market_price_min, stored.market_price_new, stored.market_price_max) == (2490, 2490, 2490)


def test_no_verified_price_asks_for_a_new_search_once(db, seller, agent_account, caplog):
    caplog.set_level("INFO", logger="agent")
    listing_id = publish(db, seller)
    messages = happy_path()[:2] + [
        AIMessage(content="", tool_calls=[call("save_assessment", save_args(web_prices=[900]), "x")]),
        AIMessage(content="", tool_calls=[call("tavily_search", {"query": "אופני הרים חדשים"}, "y")]),
    ] + happy_path()[2:]

    tavily = run_agent(messages)

    assert "none of web_prices appears in the web results" in caplog.text
    assert len(tavily.calls) == 2
    assert db.get(Assessment, listing_id).market_price_new == 2490


def test_still_no_verified_price_is_saved_as_neutral_with_low_confidence(db, seller, agent_account):
    listing_id = publish(db, seller)
    no_price = AIMessage(content="", tool_calls=[call("save_assessment", save_args(web_prices=[]), "x")])
    messages = happy_path()[:2] + [
        no_price,
        AIMessage(content="", tool_calls=[call("tavily_search", {"query": "אופני הרים חדשים"}, "y")]),
        AIMessage(content="", tool_calls=[call("save_assessment", save_args(web_prices=[]), "z")]),
        AIMessage(content="Done."),
    ]

    run_agent(messages)

    stored = db.get(Assessment, listing_id)
    assert (stored.price_vs_market, stored.price_vs_market_reason) == (MARKET_NO_PRICE, MARKET_NO_PRICE_REASON)
    assert (stored.market_price_min, stored.market_price_new, stored.confidence) == (None, None, "low")


def test_search_without_a_title_word_is_refused(db, seller, agent_account, caplog):
    caplog.set_level("INFO", logger="agent")
    listing_id = publish(db, seller)
    messages = happy_path()
    messages.insert(1, AIMessage(content="", tool_calls=[call("tavily_search", {"query": "כיסא משרדי מחיר"}, "x")]))

    tavily = run_agent(messages)

    assert "Search refused" in caplog.text
    assert [c["query"] for c in tavily.calls] == ["אופני הרים מחיר"]  # the refused one did not count
    assert db.get(Listing, listing_id).status == STATUS_EVALUATED


@pytest.mark.parametrize(
    "query, ok",
    [("אופני הרים מחיר", True), ("מחיר אופני הרים טרק", True), ("אופני הרים 27.5 מחיר", True),
     ("iphone 13 price", False), ("כיסא משרדי", False),
     ("טרק מחיר", False)],  # one title word of four is not enough
)
def test_query_mentions_title(query, ok):
    assert query_mentions_title(query, "אופני הרים טרק מרלין 7") is ok


@pytest.mark.parametrize(
    "query, ok",
    [("ספר Harry Potter 1 מחיר", True), ("harry potter מחיר", True),
     # Seen in a real run: a similar listing's title; "ספרים" is not "ספר".
     ("סדרת הארי פוטר בעברית, 7 ספרים מחיר", False)],
)
def test_query_needs_whole_title_words(query, ok):
    assert query_mentions_title(query, "ספר Harry Potter 1") is ok


def test_hebrew_prefix_is_accepted():
    assert query_mentions_title("מחיר האופניים החשמליים", "אופניים חשמליים")


def test_similar_listings_are_searched_in_the_same_category(db, seller, agent_account):
    publish(db, seller)  # category sports
    SIMILAR_CALLS.clear()

    run_agent(happy_path())

    assert SIMILAR_CALLS[0]["category"] == "sports"


def test_prices_in_text_reads_the_usual_formats():
    found = prices_in_text("מחיר 1,290 ₪ או 2490 ש\"ח, 3.200 ₪, 1,499.90 ₪, 27.5 אינץ'")

    for price in ("1290", "2490", "3200", "1499.90", "27.5"):
        assert Decimal(price) in found


def test_model_sees_only_two_save_fields(db, seller, agent_account):
    from agent.tools import SAVE_SCHEMA

    assert set(SAVE_SCHEMA["properties"]) == {"web_prices", "description_matches_title"}
