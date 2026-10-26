"""Load the sample listings into the Chroma vector database (embeddings via Ollama).

Usage: python scripts/load_sample_listings.py [--reset]
Requires Ollama running with the embedding model pulled (ollama pull bge-m3).
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.vector_store import (  # noqa: E402
    CHROMA_DIR,
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    EmbeddingError,
    ListingDocument,
    get_collection,
    index_listings,
    reset_collection,
)

SAMPLES_FILE = ROOT / "data" / "sample_listings.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Load sample listings into Chroma")
    parser.add_argument("--reset", action="store_true", help="delete the collection first")
    args = parser.parse_args()

    if args.reset:
        reset_collection()
    collection = get_collection()

    samples = json.loads(SAMPLES_FILE.read_text(encoding="utf-8"))
    listings = [ListingDocument(**item, source="sample") for item in samples]

    print(f"Embedding {len(listings)} listings with '{EMBEDDING_MODEL}'...")
    index_listings(listings, collection=collection)
    print(f"OK — collection '{COLLECTION_NAME}' in {CHROMA_DIR} now holds {collection.count()} listings.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EmbeddingError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
