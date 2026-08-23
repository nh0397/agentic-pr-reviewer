from functools import lru_cache

from sentence_transformers import SentenceTransformer

# A small, fast model run locally, no external API call and no per-call
# cost as a repository's symbol count grows into the thousands.
MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


@lru_cache
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    return model.encode(texts, show_progress_bar=False).tolist()
