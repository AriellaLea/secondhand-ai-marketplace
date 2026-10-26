"""Try the similar-listing search against the Chroma vector database.

Usage:
  python scripts/try_similar.py                      # run the built-in demo queries
  python scripts/try_similar.py --title "..." [--description "..."] [-k 5]
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.vector_store import EmbeddingError, find_similar_listings, get_collection  # noqa: E402

DEMO_QUERIES = [
    ("iPhone 13 128GB", "Used iPhone 13, black, battery 88%, with case."),
    ("אופניים לרכיבת שטח", "אופניים עם בלמי דיסק והילוכים, מצב טוב."),
    ("Sofa for living room", "Grey three-seat sofa, clean, pickup only."),
    ("ספר תכנות באנגלית", "ספר על כתיבת קוד נקי, כמו חדש."),
]


def show(title: str, description: str, k: int) -> None:
    print(f"\n» {title}")
    results = find_similar_listings(title, description, k=k)
    if not results:
        print("  (no listings in the vector database — run scripts/load_sample_listings.py)")
    for rank, item in enumerate(results, start=1):
        print(
            f"  {rank}. {item.listing_id:<10} {item.similarity:.3f}  "
            f"{item.price:>7.0f} ILS  [{item.category}]  {item.title}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Find listings similar to a given one")
    parser.add_argument("--title")
    parser.add_argument("--description", default="")
    parser.add_argument("-k", type=int, default=5)
    args = parser.parse_args()

    print(f"Vector database holds {get_collection().count()} listings.")
    queries = [(args.title, args.description)] if args.title else DEMO_QUERIES
    for title, description in queries:
        show(title, description, args.k)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except EmbeddingError as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1)
