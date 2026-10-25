"""Auth helpers: session and role checks (no business SQL here)."""

from functools import wraps

from flask import redirect, session, url_for

from app.db import get_session
from app.models.user import User


def login_user(user: User) -> None:
    session.clear()
    session["user_id"] = user.id
    session["user_role"] = user.role
    session["user_name"] = user.name


def logout_user() -> None:
    session.clear()


def current_user() -> User | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_session().get(User, user_id)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if session.get("user_id") is None:
                return redirect(url_for("auth.login"))
            if session.get("user_role") not in roles:
                return redirect(url_for("home.index"))
            return view(*args, **kwargs)

        return wrapped

    return decorator