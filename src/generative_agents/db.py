"""SQLite persistence for one run (state.sqlite).

All simulation state lives here so that a checkpoint is a committed transaction and an
interview clone is a byte copy (``Database.clone``). Provider call records live in a
separate file (provider.sqlite) committed immediately, so a step that is rolled back and
re-executed on resume hits the exact-request cache instead of re-calling a model.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  order_index INTEGER NOT NULL,
  identity_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  kind TEXT NOT NULL,
  origin TEXT NOT NULL,
  description TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_accessed_at TEXT NOT NULL,
  importance INTEGER NOT NULL,
  embedding_model TEXT NOT NULL,
  embedding_key TEXT NOT NULL,
  subject TEXT, predicate TEXT, object TEXT,
  location TEXT,
  source_event_id TEXT,
  conversation_id TEXT,
  speaker_id TEXT,
  evidence_json TEXT NOT NULL DEFAULT '[]',
  depth INTEGER NOT NULL DEFAULT 0,
  plan_id TEXT,
  seed INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(owner_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_memories_owner ON memories(owner_id, seq);

CREATE TABLE IF NOT EXISTS embeddings (
  key TEXT PRIMARY KEY,
  model TEXT NOT NULL,
  dims INTEGER NOT NULL,
  text TEXT NOT NULL,
  vector BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL,
  level TEXT NOT NULL,
  parent_id TEXT,
  day TEXT NOT NULL,
  start TEXT NOT NULL,
  duration_min INTEGER NOT NULL,
  status TEXT NOT NULL,
  json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plans_agent ON plans(agent_id, day, level, start);

CREATE TABLE IF NOT EXISTS agent_state (agent_id TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS spatial_memory (agent_id TEXT PRIMARY KEY, json TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  status TEXT NOT NULL,
  participants TEXT NOT NULL,
  json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retrieval_traces (
  id TEXT PRIMARY KEY,
  agent_id TEXT NOT NULL,
  sim_time TEXT NOT NULL,
  purpose TEXT NOT NULL,
  json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_traces_agent ON retrieval_traces(agent_id, sim_time);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  step INTEGER NOT NULL,
  sim_time TEXT NOT NULL,
  type TEXT NOT NULL,
  agent_id TEXT,
  json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_step ON events(step);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type, agent_id);

CREATE TABLE IF NOT EXISTS frames (step INTEGER PRIMARY KEY, sim_time TEXT NOT NULL, json TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS world_objects (address TEXT PRIMARY KEY, json TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS checkpoints (
  step INTEGER PRIMARY KEY,
  sim_time TEXT NOT NULL,
  json TEXT NOT NULL
);
"""


def iso(t: datetime | None) -> str | None:
    return t.isoformat() if t is not None else None


def parse_iso(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def stable_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=_json_default)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, tuple):
        return list(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, set):
        return sorted(obj)
    raise TypeError(f"not JSON serializable: {type(obj)!r}")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Database:
    """Thin wrapper over a SQLite connection with explicit transactions."""

    def __init__(self, path: str | Path | None = None, *, read_only: bool = False):
        self.path = str(path) if path else ":memory:"
        if read_only and self.path != ":memory:":
            uri = f"file:{self.path}?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        else:
            self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        if not read_only:
            self.conn.executescript(SCHEMA)
            self.conn.commit()
        self.read_only = read_only

    # ------------------------------------------------------------------ basics
    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, params)

    def executemany(self, sql: str, rows: list[tuple]) -> None:
        self.conn.executemany(sql, rows)

    def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        return self.conn.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    def commit(self) -> None:
        self.conn.commit()

    def rollback(self) -> None:
        self.conn.rollback()

    @contextmanager
    def transaction(self) -> Iterator[Database]:
        try:
            yield self
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------ meta kv
    def set_meta(self, key: str, value: Any) -> None:
        self.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, stable_json(value)),
        )

    def get_meta(self, key: str, default: Any = None) -> Any:
        row = self.one("SELECT value FROM meta WHERE key=?", (key,))
        return json.loads(row["value"]) if row else default

    # ------------------------------------------------------------------ cloning
    def clone(self, path: str | Path | None = None) -> Database:
        """Copy committed state into a new database (in memory by default).

        Interviews and evaluator probes run on clones so they cannot touch the source
        run (spec L-1, M-1, N-5).
        """

        target = Database(path)
        self.conn.commit() if not self.read_only else None
        self.conn.backup(target.conn)
        target.conn.row_factory = sqlite3.Row
        return target

    def content_hash(self, tables: tuple[str, ...] | None = None) -> str:
        """Deterministic hash of table contents, used to prove clones left the source intact."""

        h = hashlib.sha256()
        names = tables or tuple(
            r["name"] for r in self.query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name") if not r["name"].startswith("sqlite_")
        )
        for name in names:
            h.update(name.encode())
            cols = [r["name"] for r in self.query(f"PRAGMA table_info({name})")]
            order = ", ".join(cols)
            for row in self.query(f"SELECT {order} FROM {name} ORDER BY {order}"):
                h.update(repr(tuple(row)).encode())
        return h.hexdigest()
