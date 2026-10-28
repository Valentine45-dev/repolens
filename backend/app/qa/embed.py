"""Embedders. The real one loads sentence-transformers once per process; the stub is a
deterministic hashing embedder for tests and CI (design doc §19.4), so no model is downloaded.
Both return L2-normalized vectors, so cosine distance (pgvector <=>) is the right metric."""

import hashlib
import math
import re
from functools import lru_cache
from typing import Protocol

from app import config

DIM = 384  # schema.sql chunks.embedding vector(384)


class Embedder(Protocol):
    name: str
    revision: str
    dim: int
    max_tokens: int  # the model's input limit, special tokens included

    def count_tokens(self, texts: list[str]) -> list[int]:
        """Tokens each text takes as model input (special tokens included)."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    def __init__(self, model: str, revision: str):
        import transformers
        from sentence_transformers import SentenceTransformer

        transformers.logging.set_verbosity_error()  # long inputs are expected when counting
        self.model = SentenceTransformer(model, revision=revision, device="cpu")
        self.tokenizer = self.model.tokenizer
        self.name, self.revision = model, revision
        dimension = getattr(self.model, "get_embedding_dimension", None) or \
            self.model.get_sentence_embedding_dimension  # renamed in sentence-transformers 6
        self.dim = dimension()
        self.max_tokens = self.model.max_seq_length  # 256 for all-MiniLM-L6-v2 (checked)
        if self.dim != DIM:
            raise RuntimeError(f"{model} has {self.dim} dimensions; the schema expects {DIM}")

    def count_tokens(self, texts: list[str]) -> list[int]:
        encoded = self.tokenizer(texts, add_special_tokens=True, truncation=False)
        return [len(ids) for ids in encoded["input_ids"]]

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(
            texts, batch_size=config.EMBED_BATCH, normalize_embeddings=True,
            convert_to_numpy=True, show_progress_bar=False,
        )
        return vectors.tolist()


_TOKEN = re.compile(r"\w+|[^\w\s]")


class StubEmbedder:
    """Hashing bag-of-words: same text, same vector; shared words, nearby vectors."""

    name, revision, dim, max_tokens = "stub", "none", DIM, 256

    def count_tokens(self, texts: list[str]) -> list[int]:
        return [len(_TOKEN.findall(t)) + 2 for t in texts]  # +2 like [CLS] and [SEP]

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * DIM
            for word in re.findall(r"\w+", t.lower()):
                h = int.from_bytes(hashlib.blake2b(word.encode(), digest_size=4).digest(), "big")
                v[h % DIM] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    """One embedder per process (the model loads once)."""
    if config.EMBEDDER == "stub":
        return StubEmbedder()
    return SentenceTransformerEmbedder(config.EMBED_MODEL, config.EMBED_MODEL_REVISION)
