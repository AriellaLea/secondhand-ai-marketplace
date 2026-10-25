"""Application configuration. Secrets come from .env.local only."""

import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env.local")


def _database_url() -> str:
    """Read DATABASE_URL and force the psycopg2 driver (requirements.txt)."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is missing. Set it in .env.local (never hardcode it)."
        )
    # Neon may use postgresql:// or postgresql+psycopg://; we use psycopg2-binary.
    if url.startswith("postgresql+psycopg://"):
        url = "postgresql+psycopg2://" + url.removeprefix("postgresql+psycopg://")
    elif url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url.removeprefix("postgres://")
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url.removeprefix("postgresql://")
    return url


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    DATABASE_URL = _database_url()

