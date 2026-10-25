"""Command: register a new seller (write side — CQRS)."""

from dataclasses import dataclass

from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from app.models.user import User


class RegisterError(Exception):
    """Raised when registration validation fails."""


@dataclass
class RegisterSellerCommand:
    name: str
    email: str
    password: str


def handle_register_seller(session: Session, cmd: RegisterSellerCommand) -> User:
    name = (cmd.name or "").strip()
    email = (cmd.email or "").strip().lower()
    password = cmd.password or ""

    if not name:
        raise RegisterError("נא להזין שם.")
    if not email or "@" not in email:
        raise RegisterError("נא להזין כתובת אימייל תקינה.")
    if len(password) < 8:
        raise RegisterError("הסיסמה חייבת להכיל לפחות 8 תווים.")

    existing = session.query(User).filter_by(email=email).first()
    if existing is not None:
        raise RegisterError("כתובת האימייל כבר רשומה במערכת.")

    user = User(
        name=name,
        email=email,
        password_hash=generate_password_hash(password),
        role="seller",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user