"""Home controller: route only — no business logic or SQL."""

from flask import Blueprint, render_template

from app.auth import current_user, login_required

home_bp = Blueprint("home", __name__)


@home_bp.get("/")
@login_required
def index():
    return render_template("home.html", user=current_user())
