"""Fix K – the program scores the price (app/pricing.py, PRD section 6)."""

from decimal import Decimal

import pytest

import re

from app.listing_quality import score_quality
from app.pricing import (
    MARKET_NO_PRICE,
    NO_SIMILAR_SCORE,
    build_reasoning,
    score_vs_market,
    score_vs_similar,
)

D = Decimal


@pytest.mark.parametrize(
    "price, points",
    [("800", 50), ("1992", 50), ("1993", 25), ("2490", 25), ("2491", 0), ("6000", 0)],  # 0.8 x 2490 = 1992
)
def test_market_points_against_the_new_price(price, points):
    market = score_vs_market(D(price), [D("1290"), D("2490"), D("3200")])

    assert market.points == points
    assert (market.lowest, market.new_price, market.highest) == (D("1290"), D("2490"), D("3200"))


def test_median_ignores_one_wrong_price():
    # An accessory at 150 ILS slipped in: the new price barely moves.
    assert score_vs_market(D("800"), [D("150"), D("1290"), D("2490"), D("3200")]).new_price == D("1890")


def test_no_web_price_is_neutral():
    market = score_vs_market(D("800"), [])

    assert (market.points, market.new_price, market.lowest) == (MARKET_NO_PRICE, None, None)


@pytest.mark.parametrize(
    "price, points",
    [("500", 25), ("1080", 25), ("1081", 12), ("1350", 12), ("1351", 0)],  # median 900
)
def test_similar_points_against_the_similar_listings(price, points):
    assert score_vs_similar(D(price), [D("800"), D("900"), D("1000")]).points == points


def test_no_similar_listing_is_neutral():
    assert score_vs_similar(D("800"), []).points == NO_SIMILAR_SCORE


@pytest.mark.parametrize("price", ["800", "2900", "6000"])
def test_program_texts_are_hebrew_sentences(price):
    market = score_vs_market(D(price), [D("2490")])
    similar = score_vs_similar(D(price), [D("900")])
    quality = score_quality("אופניים במצב טוב", True)
    reasoning = build_reasoning([market.reason, similar.reason, quality.reason], "reject")

    for text in (market.reason, similar.reason, quality.reason, reasoning):
        # Hebrew letters, digits and punctuation only: no other script, no placeholder.
        assert re.fullmatch(r"[\u0590-\u05FF0-9 ,.()₪:]+", text)
    assert reasoning.endswith("ההמלצה: לדחות.")


@pytest.mark.parametrize(
    "description, matches, points",
    [("", True, 5), ("אופניים טובים", True, 5),  # fewer than 3 words: missing
     ("אופני הרים במצב טוב, מידה M, 21 הילוכים, בלמי דיסק, שימוש של שנתיים", True, 15),  # 13 words
     (" ".join(["מילה"] * 15), True, 25),
     (" ".join(["מילה"] * 15), False, 5)],
)
def test_listing_quality_from_length_and_the_models_answer(description, matches, points):
    assert score_quality(description, matches).points == points
