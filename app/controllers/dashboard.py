"""Dashboard controller: route only — calls a query handler, returns a view."""

from flask import Blueprint, render_template

from app.auth import current_user, role_required
from app.db import get_session
from app.models.listing import CATEGORIES, STATUS_LABELS
from app.queries.dashboard_counts import handle_dashboard_counts

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@dashboard_bp.get("")
@role_required("moderator")
def index():
    return render_template(
        "dashboard.html",
        user=current_user(),
        counts=handle_dashboard_counts(get_session()),
        categories=CATEGORIES,
        statuses=STATUS_LABELS,
    )
