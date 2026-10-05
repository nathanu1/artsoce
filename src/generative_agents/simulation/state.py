"""Per-agent runtime state persisted in state.sqlite (spec K-4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from ..db import Database, stable_json
from ..schemas import ActionState


class SummaryCache(BaseModel):
    text: str
    computed_at: datetime
    mask: str
    aspects: dict[str, str] = Field(default_factory=dict)
    memory_count: int = 0


class AgentState(BaseModel):
    agent_id: str
    tile: tuple[int, int] | None = None
    action: ActionState = Field(default_factory=ActionState)
    # reflection trigger (paper: accumulator > threshold; compat: countdown <= 0)
    reflection_accumulator: float = 0.0
    reflection_countdown: float | None = None
    reflection_ele_n: int = 0
    last_reflection_at: datetime | None = None
    reflection_retry_after: datetime | None = None
    reflections_done: int = 0
    # cached dynamic summary per mask key (Appendix A)
    summaries: dict[str, SummaryCache] = Field(default_factory=dict)
    # planning
    plan_day: str | None = None
    previous_day_summary: str | None = None
    # dialogue cooldowns: partner id -> datetime until which no new conversation starts
    cooldown_until: dict[str, datetime] = Field(default_factory=dict)
    conversation_id: str | None = None
    # reaction bookkeeping
    pending_inner_voice: list[str] = Field(default_factory=list)
    last_reaction_key: str | None = None
    failures: int = 0
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tile", mode="before")
    @classmethod
    def _tile(cls, v: Any) -> Any:
        if isinstance(v, list):
            return tuple(v)
        return v


class StateStore:
    """Identity map over agent_state rows: one live object per agent, flushed at commit."""

    def __init__(self, db: Database):
        self.db = db
        self._live: dict[str, AgentState] = {}

    def _load(self, agent_id: str) -> AgentState:
        row = self.db.one("SELECT json FROM agent_state WHERE agent_id=?", (agent_id,))
        if row is None:
            return AgentState(agent_id=agent_id)
        return AgentState.model_validate_json(row["json"])

    def get(self, agent_id: str) -> AgentState:
        if agent_id not in self._live:
            self._live[agent_id] = self._load(agent_id)
        return self._live[agent_id]

    # Backwards-compatible aliases
    load = get

    def save(self, state: AgentState) -> None:
        self._live[state.agent_id] = state
        self.db.execute(
            "INSERT INTO agent_state(agent_id, json) VALUES(?, ?) ON CONFLICT(agent_id) DO UPDATE SET json=excluded.json",
            (state.agent_id, state.model_dump_json()),
        )

    def flush(self) -> None:
        for state in self._live.values():
            self.save(state)

    def invalidate(self) -> None:
        """Drop live objects (after a rollback) so they reload from committed rows."""

        self._live.clear()

    def all(self) -> dict[str, AgentState]:
        ids = [r["agent_id"] for r in self.db.query("SELECT agent_id FROM agent_state")]
        return {i: self.get(i) for i in ids}


class EventLog:
    """Structured simulation events (events table) used by exports, metrics and the viewer."""

    def __init__(self, db: Database, step_getter: Any = None):
        self.db = db
        self.step_getter = step_getter or (lambda: 0)

    def log(self, type_: str, sim_time: datetime, agent_id: str | None = None, **data: Any) -> None:
        self.db.execute(
            "INSERT INTO events(step, sim_time, type, agent_id, json) VALUES(?,?,?,?,?)",
            (int(self.step_getter() or 0), sim_time.isoformat(), type_, agent_id, stable_json(data)),
        )

    def query(self, type_: str | None = None, agent_id: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        import json

        sql = "SELECT id, step, sim_time, type, agent_id, json FROM events WHERE 1=1"
        params: list[Any] = []
        if type_:
            sql += " AND type=?"
            params.append(type_)
        if agent_id:
            sql += " AND agent_id=?"
            params.append(agent_id)
        sql += " ORDER BY id"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        out = []
        for r in self.db.query(sql, tuple(params)):
            d = json.loads(r["json"])
            d.update({"_id": r["id"], "step": r["step"], "sim_time": r["sim_time"], "type": r["type"], "agent_id": r["agent_id"]})
            out.append(d)
        return out
