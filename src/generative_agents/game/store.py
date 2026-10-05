"""Game state in the run's database (state.sqlite), written inside the engine's transactions.

A checkpoint commits it together with the simulation; a rollback (budget, provider failure)
discards it together with the simulation. Nothing here is visible to residents.
"""

from __future__ import annotations

import json
from typing import Any

from ..db import Database, stable_json
from .world_edit import PlacedItem

GAME_SCHEMA = """
CREATE TABLE IF NOT EXISTS game_items (id TEXT PRIMARY KEY, seq INTEGER NOT NULL, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS game_requests (id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, status TEXT NOT NULL, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS game_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  step INTEGER NOT NULL,
  sim_time TEXT NOT NULL,
  kind TEXT NOT NULL,
  agent_id TEXT,
  action_seq INTEGER,
  json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_game_events_step ON game_events(step);
CREATE TABLE IF NOT EXISTS game_kv (key TEXT PRIMARY KEY, json TEXT NOT NULL);
"""

_DEFAULTS: dict[str, Any] = {
    "inventory": {},  # motif id -> count
    "found": {},  # motif id -> first time found (ISO)
    "pulse": {"points": 0, "level": 1},
    "friendship": {},  # agent id -> 0..100
    "cooldowns": {},  # object address -> ISO time it can be searched again
    "chat_hours": {},  # agent id -> "YYYY-MM-DDTHH" of the last chat that earned points
    "sparkles": [],  # social motifs left by conversations
    "seen_conversations": [],
    "requests_day": {},  # agent id -> date of the last automatic request
    "user_templates": [],
    "counters": {"item": 0, "request": 0},
    "applied_seq": 0,  # highest player action applied
    "stats": {"chats": 0, "gifts": 0, "requests_fulfilled": 0, "items_placed": 0, "motifs_found": 0, "conversations": 0},
}


class GameStore:
    def __init__(self, db: Database):
        self.db = db
        self.db.conn.executescript(GAME_SCHEMA)
        self.kv: dict[str, Any] = {}
        self._dirty: set[str] = set()
        self.load()

    # ------------------------------------------------------------------ kv
    def load(self) -> None:
        self.kv = json.loads(json.dumps(_DEFAULTS))
        for row in self.db.query("SELECT key, json FROM game_kv"):
            self.kv[row["key"]] = json.loads(row["json"])
        self._dirty.clear()

    def get(self, key: str) -> Any:
        return self.kv[key]

    def put(self, key: str, value: Any) -> None:
        self.kv[key] = value
        self._dirty.add(key)

    def touch(self, key: str) -> None:
        self._dirty.add(key)

    def flush(self) -> None:
        for key in sorted(self._dirty):
            self.db.execute(
                "INSERT INTO game_kv(key, json) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET json=excluded.json",
                (key, stable_json(self.kv[key])),
            )
        self._dirty.clear()

    def next_id(self, counter: str, prefix: str) -> str:
        counters = self.kv["counters"]
        counters[counter] = int(counters.get(counter, 0)) + 1
        self.touch("counters")
        return f"{prefix}{counters[counter]:04d}"

    # ------------------------------------------------------------------ items
    def items(self) -> list[PlacedItem]:
        return [PlacedItem.from_json(json.loads(r["json"])) for r in self.db.query("SELECT json FROM game_items ORDER BY seq")]

    def save_item(self, item: PlacedItem, seq: int | None = None) -> None:
        if seq is None:
            row = self.db.one("SELECT seq FROM game_items WHERE id=?", (item.id,))
            seq = int(row["seq"]) if row else int(item.id.lstrip("i") or 0)
        self.db.execute(
            "INSERT INTO game_items(id, seq, json) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET json=excluded.json",
            (item.id, seq, stable_json(item.to_json())),
        )

    def delete_item(self, item_id: str) -> None:
        self.db.execute("DELETE FROM game_items WHERE id=?", (item_id,))

    # ------------------------------------------------------------------ requests
    def requests(self, agent_id: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        sql, params = "SELECT json FROM game_requests WHERE 1=1", []
        if agent_id:
            sql += " AND agent_id=?"
            params.append(agent_id)
        if status:
            sql += " AND status=?"
            params.append(status)
        return [json.loads(r["json"]) for r in self.db.query(sql + " ORDER BY id", tuple(params))]

    def save_request(self, req: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT INTO game_requests(id, agent_id, status, json) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status, json=excluded.json",
            (req["id"], req["agent_id"], req["status"], stable_json(req)),
        )

    # ------------------------------------------------------------------ events
    def log(self, step: int, sim_time: str, kind: str, agent_id: str | None, payload: dict[str, Any], action_seq: int | None = None) -> int:
        cur = self.db.execute(
            "INSERT INTO game_events(step, sim_time, kind, agent_id, action_seq, json) VALUES(?,?,?,?,?,?)",
            (step, sim_time, kind, agent_id, action_seq, stable_json(payload)),
        )
        return int(cur.lastrowid or 0)

    def events(self, since_id: int = 0, limit: int = 500, kinds: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
        sql = "SELECT id, step, sim_time, kind, agent_id, action_seq, json FROM game_events WHERE id > ?"
        params: list[Any] = [since_id]
        if kinds:
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"
            params += list(kinds)
        rows = self.db.query(sql + " ORDER BY id LIMIT ?", (*params, limit))
        return [
            {
                "id": r["id"],
                "step": r["step"],
                "sim_time": r["sim_time"],
                "kind": r["kind"],
                "agent_id": r["agent_id"],
                "action_seq": r["action_seq"],
                **json.loads(r["json"]),
            }
            for r in rows
        ]
