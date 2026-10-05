"""Shared fixtures. Everything here is offline and deterministic."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from generative_agents.db import Database  # noqa: E402
from generative_agents.memory.store import MemoryStore  # noqa: E402
from generative_agents.providers.embeddings import EmbeddingService, MockHashEmbedding  # noqa: E402
from generative_agents.schemas import MemoryKind, MemoryOrigin  # noqa: E402

T0 = datetime(2023, 2, 13, 8, 0, 0)


class FixedEmbedder:
    """Test embedder that returns hand-set vectors for known texts."""

    is_fixture = True

    def __init__(self, table: dict[str, list[float]], dims: int = 3):
        self.table = table
        self.dims = dims
        self.model_id = "fixed-test"
        self.revision = "t"

    def embed(self, texts):
        return np.array([self.table.get(t, [0.0] * self.dims) for t in texts], dtype=np.float32)

    def describe(self):
        return {"kind": "fixed-test", "model": self.model_id, "dims": self.dims, "fixture": True}


class Env:
    def __init__(self, embedder=None):
        self.db = Database(None)
        self.store = MemoryStore(self.db)
        self.embedder = EmbeddingService(embedder or MockHashEmbedding(64), store=self.store)

    def add(self, owner, text, *, created=T0, importance=3, kind=MemoryKind.OBSERVATION, origin=MemoryOrigin.DIRECT_OBSERVATION, accessed=None, **fields):
        vec = self.embedder.embed_one(text)
        mem = self.store.add(
            owner_id=owner,
            kind=kind,
            origin=origin,
            description=text,
            created_at=created,
            importance=importance,
            embedding_model=self.embedder.model_key,
            vector=vec,
            **fields,
        )
        if accessed is not None:
            self.store.touch([mem.id], accessed)
            mem.last_accessed_at = accessed
        return mem


@pytest.fixture
def env():
    return Env()


@pytest.fixture
def t0():
    return T0


def hours(n: float) -> timedelta:
    return timedelta(hours=n)
