"""Auth controller: routes only — calls command/query handlers, returns views."""

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.auth import login_user, logout_user
from app.commands.register_seller import RegisterError, RegisterSellerCommand, handle_register_seller
from app.db import get_session
from app.queries.authenticate_user import AuthError, AuthenticateUserQuery, handle_authenticate_user

auth_bp = Blueprint("auth", __name__)


@auth_bp.get("/register")
def register():
    return render_template("register.html")


@auth_bp.post("/register")
def register_post():
    cmd = RegisterSellerCommand(
        name=request.form.get("name", ""),
        email=request.form.get("email", ""),
        password=request.form.get("password", ""),
    )
    try:
        user = handle_register_seller(get_session(), cmd)
    except RegisterError as exc:
        flash(str(exc), "error")
        return render_template("register.html"), 400

    login_user(user)
    flash("ההרשמה הצליחה. ברוכים הבאים!", "ok")
    return redirect(url_for("home.index"))


@auth_bp.get("/login")
def login():
    return render_template("login.html")


@auth_bp.post("/login")
def login_post():
    query = AuthenticateUserQuery(
        email=request.form.get("email", ""),
        password=request.form.get("password", ""),
    )
    try:
        user = handle_authenticate_user(get_session(), query)
    except AuthError as exc:
        flash(str(exc), "error")
        return render_template("login.html"), 401

    login_user(user)
    return redirect(url_for("home.index"))


@auth_bp.post("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))