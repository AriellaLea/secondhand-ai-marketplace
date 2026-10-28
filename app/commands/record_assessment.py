"""Command: the AI agent records its assessment of a listing (write side — CQRS + Event Sourcing).

The agent's program sends the three sub-scores (it computes the two price ones itself,
see app/pricing.py); this command adds them up and derives the recommendation and the
confidence (PRD section 6). Error messages are in English
because only the agent's LLM reads them.
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.commands.publish_listing import PRICE_MAX
from app.events.projections import project
from app.events.store import append_event
from app.events.types import LISTING_EVALUATED
from app.models.assessment import (
    APPROVE_FROM,
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    LISTING_QUALITY_MAX,
    MANUAL_REVIEW_FROM,
    PRICE_VS_MARKET_MAX,
    PRICE_VS_SIMILAR_MAX,
    RECOMMENDATION_APPROVE,
    RECOMMENDATION_MANUAL_REVIEW,
    RECOMMENDATION_REJECT,
)
from app.models.listing import STATUS_EVALUATED, STATUS_PENDING_EVALUATION, Listing
from app.models.user import AGENT_EMAIL, ROLE_AGENT, User

REASON_MAX = 1000
REASONING_MAX = 5000
SIMILAR_IDS_MAX = 20
# Confidence drops when the market range is this wide (max more than twice min).
WIDE_RANGE_FACTOR = 2
HIGH_CONFIDENCE_MIN_SIMILAR = 3


class RecordAssessmentError(Exception):
    """Raised when the assessment cannot be recorded."""


@dataclass
class RecordAssessmentCommand:
    listing_id: str
    price_vs_market: int
    price_vs_market_reason: str
    price_vs_similar: int
    price_vs_similar_reason: str
    listing_quality: int
    listing_quality_reason: str
    # All three or none (no price found on the web); market_price_new is their median.
    market_price_min: float | str | None
    market_price_max: float | str | None
    similar_listing_ids: list[str] = field(default_factory=list)
    reasoning: str = ""
    market_price_new: float | str | None = None


@dataclass(frozen=True)
class RecordedAssessment:
    listing_id: str
    score: int
    recommendation: str
    confidence: str
    status: str


def _sub_score(name: str, value, maximum: int) -> int:
    # A small LLM may send 40, 40.0 or "40"; anything else is refused.
    if isinstance(value, bool):
        value = None
    elif isinstance(value, float) and value.is_integer():
        value = int(value)
    elif isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if not isinstance(value, int) or not 0 <= value <= maximum:
        raise RecordAssessmentError(f"{name} must be a whole number from 0 to {maximum}.")
    return value


def _text(name: str, value, maximum: int) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        raise RecordAssessmentError(f"{name} is required and cannot be empty.")
    if len(text) > maximum:
        raise RecordAssessmentError(f"{name} can be at most {maximum} characters.")
    return text


def _market_price(name: str, value) -> Decimal:
    try:
        price = Decimal(str(value).strip().replace(",", ""))
    except InvalidOperation:
        raise RecordAssessmentError(f"{name} must be a number in ILS.") from None
    if not price.is_finite() or price <= 0 or price > PRICE_MAX:
        raise RecordAssessmentError(f"{name} must be a positive price in ILS.")
    return price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _market_prices(cmd: RecordAssessmentCommand) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    given = [cmd.market_price_min, cmd.market_price_max, cmd.market_price_new]
    if all(value is None for value in given):
        return None, None, None  # no price was found on the web
    if any(value is None for value in given):
        raise RecordAssessmentError(
            "Send market_price_min, market_price_max and market_price_new together, or none of them."
        )
    market_min = _market_price("market_price_min", cmd.market_price_min)
    market_max = _market_price("market_price_max", cmd.market_price_max)
    market_new = _market_price("market_price_new", cmd.market_price_new)
    if not market_min <= market_new <= market_max:
        raise RecordAssessmentError(
            "market_price_new must be between market_price_min and market_price_max."
        )
    return market_min, market_max, market_new


def _optional_str(value: Decimal | None) -> str | None:
    return None if value is None else str(value)


def _similar_ids(value, own_id: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RecordAssessmentError("similar_listing_ids must be a list of listing id strings.")
    ids = []
    for item in value:
        item = item.strip()
        if item and item != own_id and item not in ids:
            ids.append(item)
    if len(ids) > SIMILAR_IDS_MAX:
        raise RecordAssessmentError(f"similar_listing_ids can hold at most {SIMILAR_IDS_MAX} ids.")
    return ids


def recommendation_for(score: int) -> str:
    if score >= APPROVE_FROM:
        return RECOMMENDATION_APPROVE
    if score >= MANUAL_REVIEW_FROM:
        return RECOMMENDATION_MANUAL_REVIEW
    return RECOMMENDATION_REJECT


def confidence_for(similar_count: int, market_min: Decimal | None, market_max: Decimal | None) -> str:
    if similar_count == 0 or market_min is None:
        return CONFIDENCE_LOW
    wide_range = market_max > market_min * WIDE_RANGE_FACTOR
    if similar_count >= HIGH_CONFIDENCE_MIN_SIMILAR and not wide_range:
        return CONFIDENCE_HIGH
    return CONFIDENCE_MEDIUM


def handle_record_assessment(session: Session, cmd: RecordAssessmentCommand) -> RecordedAssessment:
    agent = session.query(User).filter_by(email=AGENT_EMAIL, role=ROLE_AGENT).first()
    if agent is None:
        raise RecordAssessmentError(
            "The agent service account is missing. Run scripts/create_agent_user.py first."
        )

    listing = session.get(Listing, (cmd.listing_id or "").strip())
    if listing is None:
        raise RecordAssessmentError(
            f"No listing with id {cmd.listing_id!r}. Use the id returned by get_pending_listing."
        )
    # A listing is evaluated once; the moderator decides what happens next.
    if listing.status != STATUS_PENDING_EVALUATION:
        raise RecordAssessmentError(
            f"Listing {listing.id} is not Pending evaluation (status: {listing.status}); nothing was saved. "
            "Call get_pending_listing for the next listing."
        )

    price_vs_market = _sub_score("price_vs_market", cmd.price_vs_market, PRICE_VS_MARKET_MAX)
    price_vs_similar = _sub_score("price_vs_similar", cmd.price_vs_similar, PRICE_VS_SIMILAR_MAX)
    listing_quality = _sub_score("listing_quality", cmd.listing_quality, LISTING_QUALITY_MAX)
    price_vs_market_reason = _text("price_vs_market_reason", cmd.price_vs_market_reason, REASON_MAX)
    price_vs_similar_reason = _text("price_vs_similar_reason", cmd.price_vs_similar_reason, REASON_MAX)
    listing_quality_reason = _text("listing_quality_reason", cmd.listing_quality_reason, REASON_MAX)
    reasoning = _text("reasoning", cmd.reasoning, REASONING_MAX)

    market_min, market_max, market_new = _market_prices(cmd)

    similar_ids = _similar_ids(cmd.similar_listing_ids, listing.id)

    score = price_vs_market + price_vs_similar + listing_quality
    recommendation = recommendation_for(score)
    confidence = confidence_for(len(similar_ids), market_min, market_max)

    # The computed values go into the event too, so a replay gives back exactly
    # what was decided at the time, even if the thresholds change later.
    event = append_event(
        session,
        listing_id=listing.id,
        event_type=LISTING_EVALUATED,
        payload={
            "score": score,
            "price_vs_market": price_vs_market,
            "price_vs_market_reason": price_vs_market_reason,
            "price_vs_similar": price_vs_similar,
            "price_vs_similar_reason": price_vs_similar_reason,
            "listing_quality": listing_quality,
            "listing_quality_reason": listing_quality_reason,
            "recommendation": recommendation,
            "confidence": confidence,
            "market_price_min": _optional_str(market_min),
            "market_price_max": _optional_str(market_max),
            "market_price_new": _optional_str(market_new),
            "similar_listing_ids": similar_ids,
            "reasoning": reasoning,
        },
        actor_id=agent.id,
    )
    project(session, event)
    session.commit()  # event and read model are saved together or not at all
    return RecordedAssessment(
        listing_id=listing.id,
        score=score,
        recommendation=recommendation,
        confidence=confidence,
        status=STATUS_EVALUATED,
    )
