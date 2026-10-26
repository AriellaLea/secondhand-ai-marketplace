"""Listings controller: routes only — calls command and query handlers, returns views."""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.auth import current_user, login_required, role_required
from app.commands.publish_listing import (
    PublishListingCommand,
    PublishListingError,
    handle_publish_listing,
)
from app.db import get_session
from app.models.listing import CATEGORIES, STATUS_LABELS
from app.queries.get_listing_details import (
    GetListingDetailsQuery,
    ListingNotFoundError,
    handle_get_listing_details,
)
from app.queries.list_listings import ListListingsQuery, handle_list_listings
from app.queries.listing_read_model import Viewer
from app.queries.search_listings import SearchListingsQuery, handle_search_listings

listings_bp = Blueprint("listings", __name__, url_prefix="/listings")


def _viewer() -> Viewer:
    return Viewer(user_id=session["user_id"], role=session["user_role"])


@listings_bp.get("")
@login_required
def index():
    table = handle_list_listings(
        get_session(),
        ListListingsQuery(
            viewer=_viewer(),
            sort=request.args.get("sort", ""),
            direction=request.args.get("dir", ""),
            status=request.args.get("status", ""),
        ),
    )
    return render_template(
        "listings_table.html",
        user=current_user(),
        table=table,
        categories=CATEGORIES,
        statuses=STATUS_LABELS,
    )


@listings_bp.get("/search")
@login_required
def search():
    query = SearchListingsQuery(
        viewer=_viewer(),
        keyword=request.args.get("q", ""),
        category=request.args.get("category", ""),
    )
    results = handle_search_listings(get_session(), query)
    return render_template(
        "search.html",
        user=current_user(),
        query=query,
        results=results,
        categories=CATEGORIES,
        statuses=STATUS_LABELS,
    )


@listings_bp.get("/<listing_id>")
@login_required
def show(listing_id):
    try:
        details = handle_get_listing_details(
            get_session(), GetListingDetailsQuery(viewer=_viewer(), listing_id=listing_id)
        )
    except ListingNotFoundError as exc:
        return render_template("not_found.html", user=current_user(), message=str(exc)), 404
    return render_template(
        "listing_details.html",
        user=current_user(),
        details=details,
        categories=CATEGORIES,
        statuses=STATUS_LABELS,
    )


@listings_bp.get("/new")
@role_required("seller")
def new():
    return render_template(
        "new_listing.html", user=current_user(), categories=CATEGORIES, form={}
    )


@listings_bp.post("")
@role_required("seller")
def create():
    cmd = PublishListingCommand(
        seller_id=session["user_id"],
        title=request.form.get("title", ""),
        description=request.form.get("description", ""),
        price=request.form.get("price", ""),
        category=request.form.get("category", ""),
    )
    try:
        handle_publish_listing(get_session(), cmd)
    except PublishListingError as exc:
        flash(str(exc), "error")
        return (
            render_template(
                "new_listing.html",
                user=current_user(),
                categories=CATEGORIES,
                form=request.form,
            ),
            400,
        )

    flash("המודעה פורסמה בהצלחה ונמצאת בסטטוס: ממתינה להערכה.", "ok")
    return redirect(url_for("listings.index"))
