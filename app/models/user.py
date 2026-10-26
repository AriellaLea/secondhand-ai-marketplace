"""User read model (authentication and roles)."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ROLE_SELLER = "seller"
ROLE_MODERATOR = "moderator"
# Service account that the AI agent acts as in the event log. It can never log in.
ROLE_AGENT = "agent"
AGENT_EMAIL = "agent@system.local"
AGENT_NAME = "סוכן AI"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # seller | moderator | agent