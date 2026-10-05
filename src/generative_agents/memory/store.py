"""Append-only, per-agent memory stream backed by SQLite (spec B-1 to B-4).

Memories are never deleted or rewritten; only ``last_accessed_at`` changes, and only for
memories actually delivered by retrieval (spec C-7).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any

import numpy as np

from ..db import Database, iso, parse_iso, sha256_text, stable_json
from ..schemas import Memory, MemoryKind, MemoryOrigin


def embedding_key(model: str, text: str) -> str:
    return sha256_text(f"{model}␟{text}")


class MemoryStore:
    def __init__(self, db: Database):
        self.db = db
        self._seq_cache: dict[str, int] = {}

    # ------------------------------------------------------------------ writes
    def next_id(self, owner_id: str) -> tuple[str, int]:
        if owner_id not in self._seq_cache:
            row = self.db.one("SELECT MAX(seq) AS s FROM memories WHERE owner_id=?", (owner_id,))
            self._seq_cache[owner_id] = int(row["s"] or 0)
        self._seq_cache[owner_id] += 1
        seq = self._seq_cache[owner_id]
        return f"{owner_id}.m{seq:05d}", seq

    def reset_seq_cache(self) -> None:
        self._seq_cache.clear()

    def add(
        self,
        *,
        owner_id: str,
        kind: MemoryKind,
        origin: MemoryOrigin,
        description: str,
        created_at: datetime,
        importance: int,
        embedding_model: str,
        vector: np.ndarray | None = None,
        **fields: Any,
    ) -> Memory:
        if not description or not description.strip():
            raise ValueError("memory description must be non-empty")
        mem_id, seq = self.next_id(owner_id)
        mem = Memory(
            id=mem_id,
            owner_id=owner_id,
            kind=kind,
            origin=origin,
            description=description.strip(),
            created_at=created_at,
            last_accessed_at=created_at,
            importance=int(importance),
            embedding_model=embedding_model,
            **fields,
        )
        key = embedding_key(embedding_model, mem.description)
        self.db.execute(
            """INSERT INTO memories(id, owner_id, seq, kind, origin, description, created_at,
                 last_accessed_at, importance, embedding_model, embedding_key, subject, predicate,
                 object, location, source_event_id, conversation_id, speaker_id, evidence_json,
                 depth, plan_id, seed, metadata_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                mem.id, mem.owner_id, seq, mem.kind.value, mem.origin.value, mem.description,
                iso(mem.created_at), iso(mem.last_accessed_at), mem.importance, embedding_model, key,
                mem.subject, mem.predicate, mem.object, mem.location, mem.source_event_id,
                mem.conversation_id, mem.speaker_id, json.dumps(mem.evidence_ids), mem.depth,
                mem.plan_id, 1 if mem.seed else 0, stable_json(mem.metadata),
            ),
        )
        if vector is not None:
            self.put_vector(embedding_model, mem.description, vector)
        return mem

    def put_vector(self, model: str, text: str, vector: np.ndarray) -> str:
        key = embedding_key(model, text)
        vec = np.asarray(vector, dtype=np.float32)
        self.db.execute(
            "INSERT OR IGNORE INTO embeddings(key, model, dims, text, vector) VALUES(?,?,?,?,?)",
            (key, model, int(vec.shape[0]), text, vec.tobytes()),
        )
        return key

    def get_vector(self, model: str, text: str) -> np.ndarray | None:
        row = self.db.one("SELECT vector FROM embeddings WHERE key=?", (embedding_key(model, text),))
        if row is None:
            return None
        return np.frombuffer(row["vector"], dtype=np.float32).copy()

    def touch(self, memory_ids: Iterable[str], when: datetime) -> None:
        rows = [(iso(when), mid) for mid in memory_ids]
        if rows:
            self.db.executemany("UPDATE memories SET last_accessed_at=? WHERE id=?", rows)

    # ------------------------------------------------------------------ reads
    @staticmethod
    def _row_to_memory(row: Any) -> Memory:
        return Memory(
            id=row["id"],
            owner_id=row["owner_id"],
            kind=MemoryKind(row["kind"]),
            origin=MemoryOrigin(row["origin"]),
            description=row["description"],
            created_at=parse_iso(row["created_at"]),
            last_accessed_at=parse_iso(row["last_accessed_at"]),
            importance=row["importance"],
            embedding_model=row["embedding_model"],
            subject=row["subject"],
            predicate=row["predicate"],
            object=row["object"],
            location=row["location"],
            source_event_id=row["source_event_id"],
            conversation_id=row["conversation_id"],
            speaker_id=row["speaker_id"],
            evidence_ids=json.loads(row["evidence_json"]),
            depth=row["depth"],
            plan_id=row["plan_id"],
            seed=bool(row["seed"]),
            metadata=json.loads(row["metadata_json"]),
        )

    def get(self, memory_id: str) -> Memory | None:
        row = self.db.one("SELECT * FROM memories WHERE id=?", (memory_id,))
        return self._row_to_memory(row) if row else None

    def get_many(self, memory_ids: Iterable[str]) -> list[Memory]:
        ids = list(memory_ids)
        if not ids:
            return []
        out: dict[str, Memory] = {}
        for i in range(0, len(ids), 500):
            chunk = ids[i : i + 500]
            marks = ",".join("?" for _ in chunk)
            for row in self.db.query(f"SELECT * FROM memories WHERE id IN ({marks})", tuple(chunk)):
                out[row["id"]] = self._row_to_memory(row)
        return [out[i] for i in ids if i in out]

    def for_agent(
        self,
        owner_id: str,
        *,
        kinds: Iterable[MemoryKind] | None = None,
        created_before: datetime | None = None,
        limit: int | None = None,
        newest_first: bool = False,
    ) -> list[Memory]:
        sql = "SELECT * FROM memories WHERE owner_id=?"
        params: list[Any] = [owner_id]
        if kinds is not None:
            kind_list = [k.value for k in kinds]
            if not kind_list:
                return []
            sql += f" AND kind IN ({','.join('?' for _ in kind_list)})"
            params += kind_list
        if created_before is not None:
            sql += " AND created_at <= ?"
            params.append(iso(created_before))
        sql += " ORDER BY seq DESC" if newest_first else " ORDER BY seq ASC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return [self._row_to_memory(r) for r in self.db.query(sql, tuple(params))]

    def count(self, owner_id: str) -> int:
        row = self.db.one("SELECT COUNT(*) AS n FROM memories WHERE owner_id=?", (owner_id,))
        return int(row["n"])

    def vectors_for(self, memories: list[Memory]) -> np.ndarray:
        """Stack embeddings for ``memories`` (rows align with the input order)."""

        if not memories:
            return np.zeros((0, 0), dtype=np.float32)
        keys = [embedding_key(m.embedding_model, m.description) for m in memories]
        found: dict[str, np.ndarray] = {}
        uniq = list(dict.fromkeys(keys))
        for i in range(0, len(uniq), 500):
            chunk = uniq[i : i + 500]
            marks = ",".join("?" for _ in chunk)
            for row in self.db.query(f"SELECT key, vector FROM embeddings WHERE key IN ({marks})", tuple(chunk)):
                found[row["key"]] = np.frombuffer(row["vector"], dtype=np.float32)
        missing = [m.id for m, k in zip(memories, keys, strict=True) if k not in found]
        if missing:
            raise KeyError(f"embeddings missing for memories: {missing[:5]}")
        return np.stack([found[k] for k in keys])

    def latest_observation_triples(self, owner_id: str, n: int) -> set[tuple[str | None, str | None, str | None]]:
        """SPO triples of the latest ``n`` perceived events (released-code retention, perceive.py:122)."""

        if n <= 0:
            return set()
        rows = self.db.query(
            """SELECT subject, predicate, object FROM memories
               WHERE owner_id=? AND origin=? ORDER BY seq DESC LIMIT ?""",
            (owner_id, MemoryOrigin.DIRECT_OBSERVATION.value, n),
        )
        return {(r["subject"], r["predicate"], r["object"]) for r in rows}
