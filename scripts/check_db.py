"""Check that DATABASE_URL from .env.local connects to PostgreSQL (Neon)."""

import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env.local")

from app.config import Config  # noqa: E402


def main() -> int:
    url = Config.DATABASE_URL
    # Never print the full connection string (contains credentials).
    host_hint = url.split("@")[-1] if "@" in url else "(hidden)"
    print(f"Connecting to: {host_hint}")

    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
        version = conn.execute(text("SELECT version()")).scalar()

    print(f"OK — SELECT 1 returned {result}")
    print(f"PostgreSQL: {version}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Database connection failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
