"""Listings controller: routes only — calls command handlers, returns views."""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app.auth import current_user, role_required
from app.commands.publish_listing import (
    PublishListingCommand,
    PublishListingError,
    handle_publish_listing,
)
from app.db import get_session
from app.models.listing import CATEGORIES

listings_bp = Blueprint("listings", __name__, url_prefix="/listings")


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
    return redirect(url_for("home.index"))
