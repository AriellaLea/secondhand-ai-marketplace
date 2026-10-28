"""Upgrade an existing `assessments` table (fix K): add market_price_new and let the
market prices be empty when no price was found on the web.

create_all creates missing tables but never changes an existing one, hence this script.
Safe to run twice. Usage: python scripts/upgrade_assessments_table.py
"""

import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine, inspect, text

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env.local")

from app.config import Config  # noqa: E402


def upgrade(engine: Engine) -> list[str]:
    """Apply what is missing; returns what was changed."""
    columns = {column["name"]: column for column in inspect(engine).get_columns("assessments")}
    changes = []
    with engine.begin() as connection:
        if "market_price_new" not in columns:
            connection.execute(text("ALTER TABLE assessments ADD COLUMN market_price_new NUMERIC(10, 2)"))
            changes.append("added market_price_new")
        for name in ("market_price_min", "market_price_max"):
            # SQLite (tests) cannot change a column; the tests create the new schema directly.
            if not columns[name]["nullable"] and engine.dialect.name == "postgresql":
                connection.execute(text(f"ALTER TABLE assessments ALTER COLUMN {name} DROP NOT NULL"))
                changes.append(f"{name} may be empty")
    return changes


def main() -> int:
    engine = create_engine(Config.DATABASE_URL, pool_pre_ping=True)
    changes = upgrade(engine)
    print("Upgraded: " + ", ".join(changes) if changes else "Already up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
