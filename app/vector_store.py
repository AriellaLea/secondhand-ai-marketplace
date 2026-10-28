"""Vector database of listings (Chroma + Ollama embeddings) for similar-listing search (RAG).

The same embedding model is used to index listings and to embed the query,
otherwise the vectors would not be comparable.
"""

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import chromadb
from chromadb.config import Settings

_ROOT = Path(__file__).resolve().parent.parent

CHROMA_DIR = Path(os.getenv("CHROMA_DIR", _ROOT / "data" / "chroma"))
COLLECTION_NAME = "listings"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "bge-m3")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "127.0.0.1:11434").rstrip("/")
if "://" not in OLLAMA_HOST:  # Ollama itself accepts OLLAMA_HOST without a scheme
    OLLAMA_HOST = f"http://{OLLAMA_HOST}"

# Takes texts, returns one vector per text. Swappable so tests run without Ollama.
Embedder = Callable[[Sequence[str]], list[list[float]]]

EMBED_BATCH_SIZE = 8  # keeps each request short on an 8 GB machine
EMBED_TIMEOUT_SECONDS = 120


class EmbeddingError(Exception):
    """Raised when Ollama cannot compute the embeddings."""


def _post_embed(texts: list[str]) -> list[list[float]]:
    # Plain HTTP to Ollama's /api/embed: the `ollama` Python package hangs
    # against recent Ollama servers, the REST API does not.
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/embed",
        data=json.dumps({"model": EMBEDDING_MODEL, "input": texts}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=EMBED_TIMEOUT_SECONDS) as response:
            return json.load(response)["embeddings"]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise EmbeddingError(
            f"Ollama refused the request ({exc.code}): {detail}. "
            f"Is the model pulled? Run: ollama pull {EMBEDDING_MODEL}"
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise EmbeddingError(
            f"Cannot reach Ollama at {OLLAMA_HOST} ({exc}). Start it with: ollama serve"
        ) from exc


def ollama_embed(texts: Sequence[str]) -> list[list[float]]:
    vectors = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        vectors.extend(_post_embed(list(texts[start : start + EMBED_BATCH_SIZE])))
    return vectors


@dataclass(frozen=True)
class ListingDocument:
    listing_id: str
    title: str
    description: str
    category: str
    price: float  # ILS
    source: str = "sample"  # sample | approved


@dataclass(frozen=True)
class SimilarListing:
    listing_id: str
    title: str
    category: str
    price: float
    similarity: float  # cosine similarity, 1.0 = identical meaning


def listing_text(title: str, description: str) -> str:
    return f"{title}\n{description}"


def _client(path: Path | str):
    return chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))


def reset_collection(path: Path | str = CHROMA_DIR) -> None:
    """Drop every vector so the collection can be rebuilt from scratch."""
    client = _client(path)
    if COLLECTION_NAME in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION_NAME)


def get_collection(path: Path | str = CHROMA_DIR):
    return _client(path).get_or_create_collection(
        COLLECTION_NAME,
        configuration={"hnsw": {"space": "cosine"}},
        embedding_function=None,  # we always pass our own embeddings
    )


def index_listings(
    listings: Sequence[ListingDocument], collection=None, embed: Embedder = ollama_embed
) -> int:
    """Add or update listings in the vector database. Re-running is safe (upsert by id)."""
    if not listings:
        return 0
    collection = collection if collection is not None else get_collection()
    collection.upsert(
        ids=[item.listing_id for item in listings],
        embeddings=embed([listing_text(item.title, item.description) for item in listings]),
        documents=[listing_text(item.title, item.description) for item in listings],
        metadatas=[
            {
                "listing_id": item.listing_id,
                "title": item.title,
                "category": item.category,
                "price": float(item.price),
                "source": item.source,
            }
            for item in listings
        ],
    )
    return len(listings)


def find_similar_listings(
    title: str,
    description: str,
    k: int = 5,
    exclude_id: str | None = None,
    collection=None,
    embed: Embedder = ollama_embed,
    category: str | None = None,
) -> list[SimilarListing]:
    """Return the k listings closest in meaning to the given one, most similar first.

    exclude_id skips the listing itself when it is already indexed. category keeps only
    listings of that category (bge-m3 found a baby chair "similar" to a book).
    """
    collection = collection if collection is not None else get_collection()
    n_results = min(k + (1 if exclude_id else 0), collection.count())
    if n_results <= 0:
        return []

    result = collection.query(
        query_embeddings=embed([listing_text(title, description)]),
        n_results=n_results,
        include=["metadatas", "distances"],
        where={"category": category} if category else None,
    )
    similar = []
    for listing_id, metadata, distance in zip(
        result["ids"][0], result["metadatas"][0], result["distances"][0]
    ):
        if listing_id == exclude_id:
            continue
        similar.append(
            SimilarListing(
                listing_id=listing_id,
                title=metadata["title"],
                category=metadata["category"],
                price=metadata["price"],
                similarity=round(1 - distance, 4),
            )
        )
    return similar[:k]
