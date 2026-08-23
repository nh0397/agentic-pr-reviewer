from functools import lru_cache

from fastembed import TextEmbedding

# fastembed (from the Qdrant team) runs this model locally via ONNX Runtime,
# not PyTorch. Same idea as sentence-transformers, zero external API calls,
# zero per-call cost, but without dragging in torch, which is hundreds of MB
# and slow to build/import for what is otherwise a small, fast model.
MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384


@lru_cache
def get_embedding_model() -> TextEmbedding:
    return TextEmbedding(model_name=MODEL_NAME)


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    return [vector.tolist() for vector in model.embed(texts)]
