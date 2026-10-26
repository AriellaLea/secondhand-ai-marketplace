"""Query: listing counts by status and by category (read side — CQRS, F6)."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.listing import CATEGORIES, STATUS_LABELS, Listing


@dataclass(frozen=True)
class DashboardCounts:
    # Every status and category is present, with 0 when there are no listings.
    by_status: dict[str, int]
    by_category: dict[str, int]
    total: int


def _count_by(session: Session, column, keys) -> dict[str, int]:
    found = dict(session.execute(select(column, func.count()).group_by(column)).all())
    return {key: found.get(key, 0) for key in keys}


def handle_dashboard_counts(session: Session) -> DashboardCounts:
    by_status = _count_by(session, Listing.status, STATUS_LABELS)
    by_category = _count_by(session, Listing.category, CATEGORIES)
    return DashboardCounts(
        by_status=by_status,
        by_category=by_category,
        total=sum(by_status.values()),
    )
