"""Phase 6 – Vector database: indexing and similar-listing search.

Uses a fake keyword embedder and a temporary Chroma folder, so Ollama is not needed.
"""

import json
import re
from pathlib import Path

import pytest

from app.models.listing import CATEGORIES
from app.vector_store import (
    ListingDocument,
    find_similar_listings,
    get_collection,
    index_listings,
    reset_collection,
)

SAMPLES_FILE = Path(__file__).resolve().parent.parent / "data" / "sample_listings.json"
VOCAB = ["phone", "bike", "sofa", "book", "black", "mountain"]


def fake_embed(texts):
    """One dimension per vocabulary word, plus a constant so no vector is all zeros."""
    return [[1.0 if word in text.lower() else 0.0 for word in VOCAB] + [0.1] for text in texts]


@pytest.fixture
def collection(tmp_path):
    collection = get_collection(tmp_path)
    index_listings(
        [
            ListingDocument("l-phone", "Black phone", "A phone in good condition", "electronics", 900),
            ListingDocument("l-bike", "Mountain bike", "A bike for mountain trails", "sports", 1200),
            ListingDocument("l-sofa", "Grey sofa", "A three seat sofa", "furniture", 1500),
            ListingDocument("l-book", "Cooking book", "A book of recipes", "books", 60),
        ],
        collection=collection,
        embed=fake_embed,
    )
    return collection


def test_index_stores_listings_with_metadata(collection):
    stored = collection.get(ids=["l-bike"], include=["metadatas"])

    assert collection.count() == 4
    assert stored["metadatas"][0] == {
        "listing_id": "l-bike",
        "title": "Mountain bike",
        "category": "sports",
        "price": 1200.0,
        "source": "sample",
    }


def test_find_similar_returns_closest_first_with_ids(collection):
    results = find_similar_listings("Old bike", "mountain bike", k=2, collection=collection, embed=fake_embed)

    assert [r.listing_id for r in results][0] == "l-bike"
    assert len(results) == 2
    assert results[0].similarity > results[1].similarity
    assert results[0].category == "sports"
    assert results[0].price == 1200.0


def test_exclude_id_skips_the_listing_itself(collection):
    results = find_similar_listings(
        "Mountain bike", "A bike for mountain trails", k=3,
        exclude_id="l-bike", collection=collection, embed=fake_embed,
    )

    assert "l-bike" not in [r.listing_id for r in results]
    assert len(results) == 3


def test_k_larger_than_collection(collection):
    results = find_similar_listings("phone", "", k=50, collection=collection, embed=fake_embed)
    assert len(results) == 4


def test_reindexing_is_idempotent(collection):
    index_listings(
        [ListingDocument("l-bike", "Mountain bike", "A bike for mountain trails", "sports", 1100)],
        collection=collection,
        embed=fake_embed,
    )

    assert collection.count() == 4
    assert collection.get(ids=["l-bike"], include=["metadatas"])["metadatas"][0]["price"] == 1100.0


def test_empty_collection_returns_nothing(tmp_path):
    assert find_similar_listings("phone", "", collection=get_collection(tmp_path), embed=fake_embed) == []


def test_reset_collection_empties_it(tmp_path, collection):
    reset_collection(tmp_path)
    assert get_collection(tmp_path).count() == 0


def test_sample_listings_file_is_valid():
    samples = json.loads(SAMPLES_FILE.read_text(encoding="utf-8"))
    hebrew = re.compile(r"[֐-׿]")

    assert 25 <= len(samples) <= 40
    assert len({s["listing_id"] for s in samples}) == len(samples)
    assert {s["category"] for s in samples} == set(CATEGORIES)
    assert all(s["price"] > 0 and s["title"].strip() and s["description"].strip() for s in samples)
    assert any(hebrew.search(s["title"]) for s in samples)
    assert any(not hebrew.search(s["title"]) for s in samples)
    for s in samples:
        ListingDocument(**s)  # every entry has exactly the expected fields
