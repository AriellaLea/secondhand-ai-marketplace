"""Listing read model (kept up to date by projections — CQRS)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Category key -> Hebrew label (PRD section 5).
CATEGORIES = {
    "electronics": "אלקטרוניקה",
    "furniture": "רהיטים",
    "sports": "ספורט",
    "clothing": "ביגוד",
    "books": "ספרים",
    "other": "אחר",
}

STATUS_PENDING_EVALUATION = "pending_evaluation"

STATUS_LABELS = {
    STATUS_PENDING_EVALUATION: "ממתינה להערכה",
}


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # ILS
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
