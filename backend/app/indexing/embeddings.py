from collections.abc import Callable
from functools import lru_cache

from fastembed import TextEmbedding

# fastembed (from the Qdrant team) runs this model locally via ONNX Runtime,
# not PyTorch. Same idea as sentence-transformers, zero external API calls,
# zero per-call cost, but without dragging in torch, which is hundreds of MB
# and slow to build/import for what is otherwise a small, fast model.
MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384

# Embedding a large repository is the slowest part of indexing. Working in
# batches means progress can be reported as it goes, instead of one opaque
# call that looks frozen for minutes, and keeps peak memory bounded.
BATCH_SIZE = 64


@lru_cache
def get_embedding_model() -> TextEmbedding:
    return TextEmbedding(model_name=MODEL_NAME)


def embed_texts(
    texts: list[str],
    on_progress: Callable[[int, int], None] | None = None,
) -> list[list[float]]:
    """
    `on_progress(done, total)` is called after each batch so callers can
    report how far along the run is.
    """
    model = get_embedding_model()
    total = len(texts)
    vectors: list[list[float]] = []

    for start in range(0, total, BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        vectors.extend(vector.tolist() for vector in model.embed(batch))
        if on_progress is not None:
            on_progress(len(vectors), total)

    return vectors
