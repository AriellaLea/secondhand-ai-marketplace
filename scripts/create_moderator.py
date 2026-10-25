"""Create a moderator account directly in the database (no public sign-up)."""

import argparse
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
from app.models.user import User  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a moderator user")
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    if len(args.password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 1

    engine = create_engine(Config.DATABASE_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    email = args.email.strip().lower()
    if session.query(User).filter_by(email=email).first():
        print(f"User already exists: {email}", file=sys.stderr)
        return 1

    user = User(
        name=args.name.strip(),
        email=email,
        password_hash=generate_password_hash(args.password),
        role="moderator",
    )
    session.add(user)
    session.commit()
    print(f"Moderator created: {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main()) 