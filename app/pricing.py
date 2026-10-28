"""Price sub-scores and their Hebrew reasons, computed by the program, not by the model (PRD section 6).

The model only reports the prices it read on the web; their median is taken as the
new-item price; a second-hand item should cost clearly less than new. A median is
used because one wrong price (an accessory, a typo) barely moves it.
"""

from dataclasses import dataclass
from decimal import Decimal
from statistics import median

from app.models.assessment import RECOMMENDATION_LABELS

# Price vs market (out of 50): at most 80% of the new price; up to the new price; above it.
MARKET_FAIR = 50
MARKET_CLOSE_TO_NEW = 25
MARKET_ABOVE_NEW = 0
MARKET_FAIR_FACTOR = Decimal("0.8")
# No price found on the web: neutral points.
MARKET_NO_PRICE = 25
MARKET_NO_PRICE_REASON = "לא נמצאו מחירים באינטרנט."

# Price vs similar listings (out of 25), against the median of their prices.
SIMILAR_FAIR = 25
SIMILAR_SLIGHTLY_ABOVE = 12
SIMILAR_FAR_ABOVE = 0
SIMILAR_FAIR_FACTOR = Decimal("1.2")
SIMILAR_SLIGHTLY_ABOVE_FACTOR = Decimal("1.5")
# No similar listing found: neutral points.
NO_SIMILAR_SCORE = 12
NO_SIMILAR_REASON = "לא נמצאו מודעות דומות להשוואה, ולכן ניתן ציון ביניים."


@dataclass(frozen=True)
class MarketPrice:
    points: int
    reason: str
    new_price: Decimal | None  # median of the web prices
    lowest: Decimal | None
    highest: Decimal | None


@dataclass(frozen=True)
class SimilarPrice:
    points: int
    reason: str


def _ils(amount: Decimal) -> str:
    return f"{amount:,.0f}"


def _median(prices: list[Decimal]) -> Decimal:
    return Decimal(str(median(prices)))


def score_vs_market(price: Decimal, web_prices: list[Decimal]) -> MarketPrice:
    if not web_prices:
        return MarketPrice(MARKET_NO_PRICE, MARKET_NO_PRICE_REASON, None, None, None)
    new_price = _median(web_prices)
    if price <= new_price * MARKET_FAIR_FACTOR:
        points, level = MARKET_FAIR, "נמוך ממחיר"
    elif price <= new_price:
        points, level = MARKET_CLOSE_TO_NEW, "קרוב למחיר"
    else:
        points, level = MARKET_ABOVE_NEW, "גבוה ממחיר"
    reason = f"מחיר המודעה ({_ils(price)} ₪) {level} מוצר חדש באינטרנט ({_ils(new_price)} ₪)."
    return MarketPrice(points, reason, new_price, min(web_prices), max(web_prices))


def score_vs_similar(price: Decimal, similar_prices: list[Decimal]) -> SimilarPrice:
    if not similar_prices:
        return SimilarPrice(NO_SIMILAR_SCORE, NO_SIMILAR_REASON)
    middle = _median(similar_prices)
    if price <= middle * SIMILAR_FAIR_FACTOR:
        points, level = SIMILAR_FAIR, "דומה למחירי המודעות הדומות או נמוך מהם"
    elif price <= middle * SIMILAR_SLIGHTLY_ABOVE_FACTOR:
        points, level = SIMILAR_SLIGHTLY_ABOVE, "גבוה מעט ממחירי המודעות הדומות"
    else:
        points, level = SIMILAR_FAR_ABOVE, "גבוה בהרבה ממחירי המודעות הדומות"
    return SimilarPrice(points, f"מחיר המודעה ({_ils(price)} ₪) {level} ({_ils(middle)} ₪).")


def build_reasoning(reasons: list[str], recommendation: str) -> str:
    """The text for the moderator: the three reasons, then the recommendation."""
    return " ".join(reasons + [f"ההמלצה: {RECOMMENDATION_LABELS[recommendation]}."])
