"""Append-only record of every provider call (provider.sqlite).

The ledger is the cache, the replay source and the audit log at once. Rows are keyed by
``(scope, request_hash, occurrence)``: the n-th time the exact same request is made within a
scope maps to the n-th recorded response. That makes resume after a rolled-back step and
full re-simulation (``ga replay``) reproduce the original call sequence exactly, without
reusing samples across independent runs (spec O-1, O-2, K-4).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LEDGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scope TEXT NOT NULL,
  request_hash TEXT NOT NULL,
  occurrence INTEGER NOT NULL,
  step INTEGER,
  sim_time TEXT,
  task TEXT NOT NULL,
  template_id TEXT NOT NULL,
  template_hash TEXT NOT NULL,
  agent_id TEXT,
  purpose TEXT,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  served_model TEXT,
  settings_json TEXT NOT NULL,
  system TEXT NOT NULL,
  prompt TEXT NOT NULL,
  schema_json TEXT NOT NULL,
  status TEXT NOT NULL,
  raw_output TEXT,
  parsed_json TEXT,
  error TEXT,
  error_retryable INTEGER,
  validation_errors TEXT,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  tokens_estimated INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens INTEGER NOT NULL DEFAULT 0,
  cache_write_tokens INTEGER NOT NULL DEFAULT 0,
  cost_usd REAL,
  latency_ms REAL,
  attempt_kind TEXT,
  wall_time TEXT NOT NULL,
  metadata_json TEXT,
  UNIQUE(scope, request_hash, occurrence)
);
CREATE INDEX IF NOT EXISTS idx_calls_task ON calls(task);
CREATE INDEX IF NOT EXISTS idx_calls_agent ON calls(agent_id);

CREATE TABLE IF NOT EXISTS embedding_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  model TEXT NOT NULL,
  n_texts INTEGER NOT NULL,
  cached INTEGER NOT NULL,
  wall_time TEXT NOT NULL,
  latency_ms REAL
);
"""


@dataclass
class CallRecord:
    id: int
    status: str
    raw_output: str | None
    error: str | None
    error_retryable: bool
    input_tokens: int
    output_tokens: int
    served_model: str | None
    metadata: dict[str, Any]


class CallLedger:
    def __init__(self, path: str | Path | None, scope: str):
        self.path = str(path) if path else ":memory:"
        self.scope = scope
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(LEDGER_SCHEMA)
        self.conn.commit()
        self._counts: dict[str, int] = {}
        self.readonly_scope: str | None = None  # replay: read from this scope, never write

    # ------------------------------------------------------------------ occurrence counting
    def reset_counts(self, committed_step: int | None) -> None:
        """Initialize per-request occurrence counters from calls in committed steps.

        Calls recorded after ``committed_step`` belong to a step that was rolled back; their
        rows stay in the ledger and are reused in order when the step re-executes.
        """

        self._counts.clear()
        scope = self.readonly_scope or self.scope
        if committed_step is None:
            return
        for row in self.conn.execute(
            "SELECT request_hash, COUNT(*) AS n FROM calls WHERE scope=? AND step<=? GROUP BY request_hash",
            (scope, committed_step),
        ):
            self._counts[row["request_hash"]] = int(row["n"])

    def next_occurrence(self, request_hash: str) -> int:
        n = self._counts.get(request_hash, 0)
        self._counts[request_hash] = n + 1
        return n

    # ------------------------------------------------------------------ lookup / record
    def lookup(self, request_hash: str, occurrence: int) -> CallRecord | None:
        scope = self.readonly_scope or self.scope
        row = self.conn.execute(
            "SELECT * FROM calls WHERE scope=? AND request_hash=? AND occurrence=?",
            (scope, request_hash, occurrence),
        ).fetchone()
        if row is None:
            return None
        return CallRecord(
            id=row["id"],
            status=row["status"],
            raw_output=row["raw_output"],
            error=row["error"],
            error_retryable=bool(row["error_retryable"]),
            input_tokens=row["input_tokens"],
            output_tokens=row["output_tokens"],
            served_model=row["served_model"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    def record(self, **fields: Any) -> int:
        if self.readonly_scope is not None:
            raise RuntimeError("ledger is read-only in replay mode")
        fields.setdefault("scope", self.scope)
        fields.setdefault("wall_time", datetime.now(UTC).isoformat())
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        cur = self.conn.execute(f"INSERT INTO calls({cols}) VALUES({marks})", tuple(fields.values()))
        self.conn.commit()
        return int(cur.lastrowid)

    def record_embedding(self, model: str, n_texts: int, cached: bool, latency_ms: float) -> None:
        if self.readonly_scope is not None:
            return
        self.conn.execute(
            "INSERT INTO embedding_calls(model, n_texts, cached, wall_time, latency_ms) VALUES(?,?,?,?,?)",
            (model, n_texts, 1 if cached else 0, datetime.now(UTC).isoformat(), latency_ms),
        )
        self.conn.commit()

    # ------------------------------------------------------------------ reporting
    def totals(self, scope: str | None = None) -> dict[str, Any]:
        scope = scope or self.scope
        row = self.conn.execute(
            """SELECT COUNT(*) AS calls,
                      SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) AS ok,
                      SUM(CASE WHEN status='invalid' THEN 1 ELSE 0 END) AS invalid,
                      SUM(CASE WHEN status IN ('error','refusal','truncated') THEN 1 ELSE 0 END) AS failed,
                      COALESCE(SUM(input_tokens),0) AS input_tokens,
                      COALESCE(SUM(output_tokens),0) AS output_tokens,
                      MAX(tokens_estimated) AS any_estimated,
                      SUM(cost_usd) AS cost_usd,
                      COUNT(cost_usd) AS priced_calls
               FROM calls WHERE scope=?""",
            (scope,),
        ).fetchone()
        out = dict(row)
        out["cost_usd"] = out["cost_usd"] if out["priced_calls"] == out["calls"] and out["calls"] else None
        by_task = {
            r["task"]: {"calls": r["n"], "input_tokens": r["i"], "output_tokens": r["o"]}
            for r in self.conn.execute(
                "SELECT task, COUNT(*) AS n, SUM(input_tokens) AS i, SUM(output_tokens) AS o FROM calls WHERE scope=? GROUP BY task ORDER BY n DESC",
                (scope,),
            )
        }
        out["by_task"] = by_task
        served = [
            r["served_model"]
            for r in self.conn.execute("SELECT DISTINCT served_model FROM calls WHERE scope=? AND served_model IS NOT NULL", (scope,))
        ]
        out["served_models"] = served
        return out

    def rows(self, scope: str | None = None, *, task: str | None = None, agent_id: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM calls WHERE scope=?"
        params: list[Any] = [scope or self.scope]
        if task:
            sql += " AND task=?"
            params.append(task)
        if agent_id:
            sql += " AND agent_id=?"
            params.append(agent_id)
        sql += " ORDER BY id"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return [dict(r) for r in self.conn.execute(sql, tuple(params))]

    def close(self) -> None:
        self.conn.close()
