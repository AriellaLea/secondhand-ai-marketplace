"""Add every approved listing to the Chroma vector database (catch-up, F8).

Approving a listing indexes it right away; if Ollama was down at that moment,
this script adds what is missing. Safe to run twice (upsert by id).
Usage: python scripts/index_approved_listings.py
"""

import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env.local")

from app.config import Config  # noqa: E402
from app.models import assessment, event, user  # noqa: E402,F401  register tables
from app.models.listing import STATUS_APPROVED, Listing  # noqa: E402
from app.vector_store import EmbeddingError, ListingDocument, index_listings  # noqa: E402


def approved_documents(session) -> list[ListingDocument]:
    return [
        ListingDocument(
            listing_id=listing.id,
            title=listing.title,
            description=listing.description,
            category=listing.category,
            price=float(listing.price),
            source="approved",
        )
        for listing in session.query(Listing).filter_by(status=STATUS_APPROVED).order_by(Listing.created_at)
    ]


def main() -> int:
    session = sessionmaker(bind=create_engine(Config.DATABASE_URL, pool_pre_ping=True))()
    documents = approved_documents(session)
    try:
        count = index_listings(documents)
    except EmbeddingError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Indexed {count} approved listings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
