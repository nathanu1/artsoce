"""Persistence for retrieval traces (spec C-11).

A trace stores the query, filters, weights, budget, and for the top-ranked candidates the raw
and normalized components and scores. To bound storage, only the first ``keep`` ranked
candidates are stored in full; the rest are summarized by count. ``ga inspect-memory``
recomputes complete rankings on demand from a snapshot without touching access times.
"""

from __future__ import annotations

import json
from typing import Any

from ..db import Database, stable_json
from .retrieval import RetrievalResult


class TraceStore:
    def __init__(self, db: Database, keep: int = 40):
        self.db = db
        self.keep = keep
        self._counts: dict[str, int] = {}

    def _next_id(self, agent_id: str) -> str:
        if agent_id not in self._counts:
            row = self.db.one("SELECT COUNT(*) AS n FROM retrieval_traces WHERE agent_id=?", (agent_id,))
            self._counts[agent_id] = int(row["n"])
        self._counts[agent_id] += 1
        return f"{agent_id}.t{self._counts[agent_id]:06d}"

    def reset(self) -> None:
        self._counts.clear()

    def sink(self, result: RetrievalResult, purpose: str | None) -> str:
        trace = result.to_trace()
        full = trace["candidates"]
        trace["candidates"] = full[: self.keep]
        trace["candidates_total"] = len(full)
        trace["candidates_truncated"] = max(0, len(full) - self.keep)
        trace["purpose"] = purpose or "unspecified"
        trace_id = self._next_id(result.agent_id)
        self.db.execute(
            "INSERT INTO retrieval_traces(id, agent_id, sim_time, purpose, json) VALUES(?,?,?,?,?)",
            (trace_id, result.agent_id, result.now.isoformat(), trace["purpose"], stable_json(trace)),
        )
        return trace_id

    def get(self, trace_id: str) -> dict[str, Any] | None:
        row = self.db.one("SELECT json FROM retrieval_traces WHERE id=?", (trace_id,))
        return json.loads(row["json"]) if row else None

    def for_agent(self, agent_id: str, limit: int = 50, purpose: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT id, json FROM retrieval_traces WHERE agent_id=?"
        params: list[Any] = [agent_id]
        if purpose:
            sql += " AND purpose=?"
            params.append(purpose)
        sql += " ORDER BY sim_time DESC, id DESC LIMIT ?"
        params.append(limit)
        out = []
        for row in self.db.query(sql, tuple(params)):
            t = json.loads(row["json"])
            t["id"] = row["id"]
            out.append(t)
        return out
