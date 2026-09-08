import logging
import os
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

# The model files are pulled from Hugging Face on first use, and its progress
# bars are written straight to the stream, which mangles our log output.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

from fastembed import TextEmbedding  # noqa: E402

logger = logging.getLogger("indexing.embeddings")

# fastembed (from the Qdrant team) runs this model locally via ONNX Runtime,
# not PyTorch. Same idea as sentence-transformers, zero external API calls,
# zero per-call cost, but without dragging in torch, which is hundreds of MB
# and slow to build/import for what is otherwise a small, fast model.
MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384

# fastembed caches model files under the system temp directory by default,
# which macOS clears periodically. That makes the model silently re-download
# mid-run and fail on a flaky connection, so keep it somewhere stable.
MODEL_CACHE_DIR = Path(__file__).resolve().parents[2] / ".model_cache"

# Embedding a large repository is the slowest part of indexing. Working in
# batches means progress can be reported as it goes, instead of one opaque
# call that looks frozen for minutes, and keeps peak memory bounded.
BATCH_SIZE = 64


@lru_cache
def get_embedding_model() -> TextEmbedding:
    MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return TextEmbedding(model_name=MODEL_NAME, cache_dir=str(MODEL_CACHE_DIR))


def warm_embedding_model() -> None:
    """
    Load (and on a fresh machine, download) the model up front. Doing this
    lazily inside a tool call means the first search in a review pays a
    multi-second download that can fail mid-review; better to absorb it at
    startup where a failure is obvious and harmless.
    """
    try:
        embed_texts(["warmup"])
        logger.info("embedding model %s ready", MODEL_NAME)
    except Exception:
        # Not fatal: the app still serves everything that does not embed.
        logger.warning("could not preload the embedding model", exc_info=True)


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
