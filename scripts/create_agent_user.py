"""Create the AI agent's service account (actor of "listing evaluated" events).

It cannot log in: the password is random and never shown, and login refuses role "agent".
Safe to run twice. Usage: python scripts/create_agent_user.py
"""

import secrets
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env.local")

from app.config import Config  # noqa: E402
from app.db import Base  # noqa: E402
from app.models.user import AGENT_EMAIL, AGENT_NAME, ROLE_AGENT, User  # noqa: E402


def main() -> int:
    engine = create_engine(Config.DATABASE_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()

    existing = session.query(User).filter_by(email=AGENT_EMAIL).first()
    if existing is not None:
        if existing.role != ROLE_AGENT:
            print(f"{AGENT_EMAIL} exists but is not the agent account.", file=sys.stderr)
            return 1
        print(f"Agent account already exists: {AGENT_EMAIL}")
        return 0

    session.add(
        User(
            name=AGENT_NAME,
            email=AGENT_EMAIL,
            password_hash=generate_password_hash(secrets.token_urlsafe(32)),
            role=ROLE_AGENT,
        )
    )
    session.commit()
    print(f"Agent account created: {AGENT_EMAIL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
