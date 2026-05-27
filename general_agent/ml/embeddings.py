from __future__ import annotations

from sentence_transformers import SentenceTransformer

_MODEL_NAME = "sentence-transformers/all-mpnet-base-v2"
_ENCODER: SentenceTransformer | None = None


def get_encoder() -> SentenceTransformer:
    """Return the module-level sentence-transformer singleton."""
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = SentenceTransformer(_MODEL_NAME)
    return _ENCODER


def encode_query(text: str) -> list[float]:
    """Encode a natural-language query into a 768-dimension normalized vector."""
    embedding = get_encoder().encode(text, normalize_embeddings=True)
    return embedding.tolist()
