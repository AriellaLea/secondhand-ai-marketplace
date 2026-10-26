"""Query: authenticate user by email and password (read side — CQRS)."""

from dataclasses import dataclass

from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash

from app.models.user import ROLE_MODERATOR, ROLE_SELLER, User


class AuthError(Exception):
    """Raised when login credentials are invalid."""


@dataclass
class AuthenticateUserQuery:
    email: str
    password: str


def handle_authenticate_user(session: Session, query: AuthenticateUserQuery) -> User:
    email = (query.email or "").strip().lower()
    password = query.password or ""

    user = session.query(User).filter_by(email=email).first()
    # Only people log in; the agent service account never does.
    if user is None or user.role not in (ROLE_SELLER, ROLE_MODERATOR):
        raise AuthError("אימייל או סיסמה שגויים.")
    if not check_password_hash(user.password_hash, password):
        raise AuthError("אימייל או סיסמה שגויים.")
    return user