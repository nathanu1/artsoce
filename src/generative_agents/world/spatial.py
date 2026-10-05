"""Private, possibly stale spatial memory (paper §5.1 p. 12; spec J-2).

Each agent keeps its own subgraph of the world tree, initialized from its official
``spatial_memory.json`` (living quarters, workplace, commonly visited places) and extended only
with areas the agent actually perceives. It also remembers the last state it saw for each
object and when, so stale beliefs are measurable.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from typing import Any

from ..db import Database


class SpatialMemory:
    def __init__(self, agent_id: str, tree: dict[str, Any] | None = None, seen_states: dict[str, Any] | None = None):
        self.agent_id = agent_id
        self.tree: dict[str, dict[str, dict[str, list[str]]]] = copy.deepcopy(tree or {})
        self.seen_states: dict[str, dict[str, str]] = dict(seen_states or {})  # address -> {state, since}
        self.dirty = False

    # ------------------------------------------------------------------ queries
    def worlds(self) -> list[str]:
        return list(self.tree)

    def sectors(self, world: str) -> list[str]:
        return sorted(self.tree.get(world, {}))

    def arenas(self, world: str, sector: str) -> list[str]:
        return sorted(self.tree.get(world, {}).get(sector, {}))

    def objects(self, world: str, sector: str, arena: str) -> list[str]:
        return sorted(set(self.tree.get(world, {}).get(sector, {}).get(arena, [])))

    def knows(self, address: str) -> bool:
        parts = address.split(":")
        node: Any = self.tree
        for i, p in enumerate(parts):
            if isinstance(node, dict):
                if p not in node:
                    return False
                node = node[p]
            elif isinstance(node, list):
                return i == len(parts) - 1 and p in node
        return True

    def counts(self) -> dict[str, int]:
        sectors = arenas = objects = 0
        for _w, secs in self.tree.items():
            sectors += len(secs)
            for _s, ars in secs.items():
                arenas += len(ars)
                for _a, objs in ars.items():
                    objects += len(set(objs))
        return {"sectors": sectors, "arenas": arenas, "objects": objects}

    # ------------------------------------------------------------------ updates
    def learn(self, world: str, sector: str, arena: str = "", obj: str = "") -> bool:
        changed = False
        secs = self.tree.setdefault(world, {})
        if sector and sector not in secs:
            secs[sector] = {}
            changed = True
        if sector and arena:
            ars = secs[sector]
            if arena not in ars:
                ars[arena] = []
                changed = True
            if obj and obj not in ars[arena]:
                ars[arena].append(obj)
                changed = True
        self.dirty = self.dirty or changed
        return changed

    def saw_state(self, address: str, state: str, when: datetime, lasting: str | None = None) -> None:
        """Record the state the agent sees; ``at`` is when it first saw the object in that state.

        ``lasting`` is the object's lasting condition at that moment. It is kept for the
        evaluator (stale-knowledge measurement) and never shown to the agent.
        """

        prev = self.seen_states.get(address)
        if prev is None or prev.get("state") != state or prev.get("lasting") != lasting:
            rec = {"state": state, "at": when.isoformat()}
            if lasting is not None:
                rec["lasting"] = lasting
            self.seen_states[address] = rec
            self.dirty = True

    def believed_state(self, address: str) -> str | None:
        rec = self.seen_states.get(address)
        return rec["state"] if rec else None

    def seen_lasting(self, address: str) -> str | None:
        rec = self.seen_states.get(address)
        return rec.get("lasting") if rec else None

    def to_json(self) -> str:
        return json.dumps({"tree": self.tree, "seen_states": self.seen_states}, sort_keys=True)

    @classmethod
    def from_json(cls, agent_id: str, text: str) -> SpatialMemory:
        d = json.loads(text)
        return cls(agent_id, d.get("tree"), d.get("seen_states"))


class SpatialStore:
    def __init__(self, db: Database):
        self.db = db
        self._live: dict[str, SpatialMemory] = {}

    def get(self, agent_id: str) -> SpatialMemory:
        if agent_id not in self._live:
            row = self.db.one("SELECT json FROM spatial_memory WHERE agent_id=?", (agent_id,))
            self._live[agent_id] = SpatialMemory.from_json(agent_id, row["json"]) if row else SpatialMemory(agent_id)
        return self._live[agent_id]

    def put(self, mem: SpatialMemory) -> None:
        self._live[mem.agent_id] = mem
        mem.dirty = True

    def flush(self) -> None:
        for mem in self._live.values():
            if mem.dirty:
                self.db.execute(
                    "INSERT INTO spatial_memory(agent_id, json) VALUES(?, ?) ON CONFLICT(agent_id) DO UPDATE SET json=excluded.json",
                    (mem.agent_id, mem.to_json()),
                )
                mem.dirty = False

    def invalidate(self) -> None:
        self._live.clear()
