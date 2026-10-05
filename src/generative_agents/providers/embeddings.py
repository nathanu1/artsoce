"""Embedding backends and a caching service.

* ``MockHashEmbedding`` — deterministic signed feature hashing of words and word pairs. It
  captures *lexical* overlap only. It is a test fixture: runs that use it are labeled MOCK and
  its retrieval results are never presented as semantic research results (spec §2).
* ``OpenAIEmbedding`` — API embeddings; model and dimensions recorded.
* ``SentenceTransformerEmbedding`` — local pretrained model from a directory or the hub cache.

Pure embedding results may be cached across runs when model, revision, dimensions and text
all match (spec O-2).
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

import numpy as np

from ..db import sha256_text
from .base import ProviderError

_WORD = re.compile(r"[a-z0-9']+")
_STOP = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being", "of", "to", "in", "on",
    "at", "for", "and", "or", "with", "by", "as", "it", "its", "this", "that", "from", "his", "her",
    "their", "they", "he", "she", "i", "you", "we", "my", "your", "our", "has", "have", "had",
}


class MockHashEmbedding:
    is_fixture = True

    def __init__(self, dims: int = 256):
        self.dims = dims
        self.model_id = f"mock-hash-{dims}"
        self.revision = "v1"

    def _features(self, text: str) -> list[tuple[str, float]]:
        words = [w for w in _WORD.findall(text.lower()) if w not in _STOP]
        feats = [(w, 1.0) for w in words]
        feats += [(f"{a}_{b}", 0.5) for a, b in zip(words, words[1:], strict=False)]
        return feats

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dims), dtype=np.float32)
        for i, text in enumerate(texts):
            for feat, weight in self._features(text):
                digest = hashlib.blake2b(feat.encode(), digest_size=8).digest()
                idx = int.from_bytes(digest[:4], "little") % self.dims
                sign = 1.0 if digest[4] & 1 else -1.0
                out[i, idx] += sign * weight
            norm = float(np.linalg.norm(out[i]))
            if norm > 0:
                out[i] /= norm
        return out

    def describe(self) -> dict[str, Any]:
        return {"kind": "mock-hash", "model": self.model_id, "dims": self.dims, "revision": self.revision, "fixture": True}


class OpenAIEmbedding:
    is_fixture = False

    def __init__(self, model: str, dims: int | None = None, timeout_s: float = 60.0):
        import openai  # optional dependency

        self.client = openai.OpenAI(timeout=timeout_s)
        self.model_id = model
        self.dims = dims or 0
        self._requested_dims = dims
        self.revision = None

    def embed(self, texts: list[str]) -> np.ndarray:
        import openai

        kwargs: dict[str, Any] = {"model": self.model_id, "input": texts}
        if self._requested_dims:
            kwargs["dimensions"] = self._requested_dims
        try:
            resp = self.client.embeddings.create(**kwargs)
        except openai.RateLimitError as exc:
            raise ProviderError(f"openai embeddings rate limited: {exc}", retryable=True) from exc
        except openai.APIStatusError as exc:
            raise ProviderError(f"openai embeddings error {exc.status_code}: {exc}", retryable=exc.status_code >= 500) from exc
        except openai.APIConnectionError as exc:
            raise ProviderError(f"openai embeddings connection error: {exc}", retryable=True) from exc
        vecs = np.array([d.embedding for d in resp.data], dtype=np.float32)
        self.dims = int(vecs.shape[1])
        return vecs

    def describe(self) -> dict[str, Any]:
        return {"kind": "openai", "model": self.model_id, "dims": self.dims or self._requested_dims, "revision": None, "fixture": False}


class SentenceTransformerEmbedding:
    is_fixture = False

    def __init__(self, model: str, local_dir: str | None = None, revision: str | None = None):
        from sentence_transformers import SentenceTransformer  # optional dependency

        source = local_dir or model
        self._model = SentenceTransformer(source, revision=revision)
        self.model_id = model
        self.revision = revision
        self.dims = int(self._model.get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self._model.encode(texts, normalize_embeddings=False), dtype=np.float32)

    def describe(self) -> dict[str, Any]:
        return {"kind": "sentence-transformers", "model": self.model_id, "dims": self.dims, "revision": self.revision, "fixture": False}


class EmbeddingCache:
    """Cross-run cache of pure embedding results keyed by (model key, text)."""

    def __init__(self, path: str | Path | None):
        self.conn: sqlite3.Connection | None = None
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.conn = sqlite3.connect(str(path), check_same_thread=False)
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, model TEXT NOT NULL, dims INTEGER NOT NULL, vector BLOB NOT NULL)"
            )
            self.conn.commit()

    def get(self, model_key: str, text: str) -> np.ndarray | None:
        if self.conn is None:
            return None
        row = self.conn.execute("SELECT vector FROM vectors WHERE key=?", (sha256_text(f"{model_key}␟{text}"),)).fetchone()
        return np.frombuffer(row[0], dtype=np.float32).copy() if row else None

    def put(self, model_key: str, text: str, vec: np.ndarray) -> None:
        if self.conn is None:
            return
        self.conn.execute(
            "INSERT OR IGNORE INTO vectors(key, model, dims, vector) VALUES(?,?,?,?)",
            (sha256_text(f"{model_key}␟{text}"), model_key, int(vec.shape[0]), np.asarray(vec, dtype=np.float32).tobytes()),
        )

    def commit(self) -> None:
        if self.conn is not None:
            self.conn.commit()


class EmbeddingService:
    """Embeds texts through the run store first, then the shared cache, then the provider."""

    def __init__(self, provider: Any, *, store: Any = None, cache: EmbeddingCache | None = None, ledger: Any = None):
        self.provider = provider
        self.store = store  # MemoryStore of the current run (keeps the run self-contained)
        self.cache = cache or EmbeddingCache(None)
        self.ledger = ledger

    @property
    def model_key(self) -> str:
        return f"{self.provider.model_id}@{self.provider.revision or 'none'}:{self.provider.dims}"

    @property
    def is_fixture(self) -> bool:
        return bool(getattr(self.provider, "is_fixture", False))

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, max(1, self.provider.dims)), dtype=np.float32)
        key = self.model_key
        result: list[np.ndarray | None] = [None] * len(texts)
        missing: list[int] = []
        for i, text in enumerate(texts):
            vec = self.store.get_vector(key, text) if self.store is not None else None
            if vec is None:
                vec = self.cache.get(key, text)
                if vec is not None and self.store is not None:
                    self.store.put_vector(key, text, vec)
            result[i] = vec
            if vec is None:
                missing.append(i)
        if missing:
            uniq = list(dict.fromkeys(texts[i] for i in missing))
            started = time.monotonic()
            vecs = self.provider.embed(uniq)
            latency = (time.monotonic() - started) * 1000
            by_text = {t: vecs[j] for j, t in enumerate(uniq)}
            for t, v in by_text.items():
                self.cache.put(key, t, v)
                if self.store is not None:
                    self.store.put_vector(key, t, v)
            self.cache.commit()
            for i in missing:
                result[i] = by_text[texts[i]]
            if self.ledger is not None:
                self.ledger.record_embedding(key, len(uniq), False, latency)
        return np.stack([np.asarray(v, dtype=np.float32) for v in result])

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]

    def describe(self) -> dict[str, Any]:
        d = dict(self.provider.describe())
        d["model_key"] = self.model_key
        return d


def build_embedding_provider(cfg: Any) -> Any:
    if cfg.kind == "mock-hash":
        return MockHashEmbedding(dims=cfg.dims or 256)
    if cfg.kind == "openai":
        return OpenAIEmbedding(cfg.model, cfg.dims)
    if cfg.kind == "sentence-transformers":
        return SentenceTransformerEmbedding(cfg.model, cfg.local_dir, cfg.revision)
    raise ValueError(f"unknown embedding provider {cfg.kind!r}")
