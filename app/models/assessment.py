"""Agent assessment read model (kept up to date by projections — CQRS). Moderators only."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Points per criterion (PRD section 6).
PRICE_VS_MARKET_MAX = 50
PRICE_VS_SIMILAR_MAX = 25
LISTING_QUALITY_MAX = 25

# Recommendation thresholds on the total score (PRD section 6, to be tuned).
APPROVE_FROM = 70
MANUAL_REVIEW_FROM = 40

RECOMMENDATION_APPROVE = "approve"
RECOMMENDATION_MANUAL_REVIEW = "manual_review"
RECOMMENDATION_REJECT = "reject"

RECOMMENDATION_LABELS = {
    RECOMMENDATION_APPROVE: "לאשר",
    RECOMMENDATION_MANUAL_REVIEW: "בדיקה ידנית",
    RECOMMENDATION_REJECT: "לדחות",
}

CONFIDENCE_LOW = "low"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_HIGH = "high"

CONFIDENCE_LABELS = {
    CONFIDENCE_LOW: "נמוכה",
    CONFIDENCE_MEDIUM: "בינונית",
    CONFIDENCE_HIGH: "גבוהה",
}


class Assessment(Base):
    __tablename__ = "assessments"

    listing_id: Mapped[str] = mapped_column(ForeignKey("listings.id"), primary_key=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    price_vs_market: Mapped[int] = mapped_column(Integer, nullable=False)
    price_vs_market_reason: Mapped[str] = mapped_column(Text, nullable=False)
    price_vs_similar: Mapped[int] = mapped_column(Integer, nullable=False)
    price_vs_similar_reason: Mapped[str] = mapped_column(Text, nullable=False)
    listing_quality: Mapped[int] = mapped_column(Integer, nullable=False)
    listing_quality_reason: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)
    market_price_min: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # ILS
    market_price_max: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # ILS
    similar_listing_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)  # Hebrew
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
