from functools import lru_cache

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.config import get_settings
from app.indexing.embeddings import EMBEDDING_DIM

COLLECTION_NAME = "code_symbols"


@lru_cache
def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(url=settings.qdrant_url or "http://localhost:6333", api_key=settings.qdrant_api_key)


def ensure_collection() -> None:
    client = get_qdrant_client()
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=qmodels.VectorParams(size=EMBEDDING_DIM, distance=qmodels.Distance.COSINE),
        )


def upsert_symbol_vectors(points: list[tuple[int, list[float], dict]]) -> None:
    """Each point is (symbol_id, vector, payload). The symbol's Postgres id
    doubles as its Qdrant point id, so looking one up from the other is a
    direct lookup, not a search."""
    ensure_collection()
    client = get_qdrant_client()
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            qmodels.PointStruct(id=symbol_id, vector=vector, payload=payload)
            for symbol_id, vector, payload in points
        ],
    )


def delete_repository_vectors(repository_id: int) -> None:
    client = get_qdrant_client()
    if not client.collection_exists(COLLECTION_NAME):
        return
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="repository_id", match=qmodels.MatchValue(value=repository_id))]
            )
        ),
    )
