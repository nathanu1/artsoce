"""Perception (paper §4.1, §5.1; released perceive.py; spec J-4).

Released-code rules, kept here:

* vision is a square of half-width ``vision_r`` around the agent's tile (maze.py:286);
* every tile in that square is added to the agent's private spatial memory;
* events are perceived only in the agent's own arena; outdoor tiles (no sector) form one
  shared "arena", so agents can meet on the street (maze.py:249 builds "world::");
* the ``att_bandwidth`` nearest events are kept, nearest first (Euclidean tile distance);
* the agent perceives its own current action (distance 0);
* objects with no event read as "<object> is idle".

Retention (dropping events whose SPO triple is among the agent's latest ``retention``
perceived events) is applied by the caller against the memory stream.

Engineering choices: visible tiles, spatial addresses and same-arena object tiles are cached
per (tile, radius); an object spanning several tiles is perceived once at its nearest tile
(the released code keeps the first tile in scan order).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from .hierarchy import WorldMap
from .spatial import SpatialMemory
from .state import IDLE, WorldState

Tile = tuple[int, int]
ArenaKey = tuple[str, str]  # (sector, arena); ("", "") is the street


@dataclass(frozen=True)
class AgentView:
    """What other agents can see of an agent at the start of a step."""

    agent_id: str
    name: str
    tile: Tile
    activity: str = ""
    predicate: str = "is"
    obj: str = ""
    address: str | None = None
    sleeping: bool = False
    conversation_id: str | None = None
    conversation_partner: str | None = None

    @property
    def description(self) -> str:
        if self.conversation_partner:
            return f"{self.name} is chatting with {self.conversation_partner}"
        return f"{self.name} is {self.activity}" if self.activity else f"{self.name} is idle"

    @property
    def spo(self) -> tuple[str, str, str]:
        if self.conversation_partner:
            return (self.name, "chat with", self.conversation_partner)
        if not self.activity:
            return (self.name, "is", IDLE)
        return (self.name, self.predicate or "is", self.obj or self.activity)


@dataclass(frozen=True)
class Percept:
    kind: str  # self | agent | object | ambient
    subject: str
    predicate: str
    object: str
    description: str
    tile: Tile
    distance: float
    agent_id: str | None = None
    address: str | None = None
    state: str | None = None

    @property
    def spo(self) -> tuple[str, str, str]:
        return (self.subject, self.predicate, self.object)

    @property
    def is_idle(self) -> bool:
        return self.description.rstrip(". ").endswith("is idle")


@dataclass
class PerceptionResult:
    agent_id: str
    tile: Tile
    arena: ArenaKey
    percepts: list[Percept] = field(default_factory=list)
    candidates: int = 0
    learned_places: int = 0


_KIND_RANK = {"self": 0, "agent": 1, "ambient": 2, "object": 3}


class Perceiver:
    def __init__(self, world: WorldMap):
        self.world = world
        self._square_cache: dict[tuple[Tile, int], tuple[tuple[str, str, str], ...]] = {}
        self._objects_cache: dict[tuple[Tile, int], tuple[tuple[str, float, Tile], ...]] = {}

    # ------------------------------------------------------------------ geometry
    def arena_key(self, tile: Tile) -> ArenaKey:
        s, a, _ = self.world.names_at(*tile)
        return (s, a)

    def in_square(self, a: Tile, b: Tile, r: int) -> bool:
        return abs(a[0] - b[0]) <= r and abs(a[1] - b[1]) <= r

    def _square(self, tile: Tile, r: int):
        x, y = tile
        for yy in range(max(0, y - r), min(self.world.height - 1, y + r) + 1):
            for xx in range(max(0, x - r), min(self.world.width - 1, x + r) + 1):
                yield xx, yy

    def visible_places(self, tile: Tile, r: int) -> tuple[tuple[str, str, str], ...]:
        """Distinct (sector, arena, object) name triples in the vision square."""

        key = (tile, r)
        hit = self._square_cache.get(key)
        if hit is None:
            seen = {self.world.names_at(xx, yy) for xx, yy in self._square(tile, r)}
            hit = tuple(sorted(t for t in seen if t[0]))
            self._square_cache[key] = hit
        return hit

    def visible_objects(self, tile: Tile, r: int) -> tuple[tuple[str, float, Tile], ...]:
        """(object address, distance, nearest tile) for objects in the same arena within vision."""

        key = (tile, r)
        hit = self._objects_cache.get(key)
        if hit is None:
            here = self.arena_key(tile)
            best: dict[str, tuple[float, Tile]] = {}
            if here[0] and here[1]:
                for xx, yy in self._square(tile, r):
                    s, a, o = self.world.names_at(xx, yy)
                    if not o or (s, a) != here:
                        continue
                    addr = f"{self.world.world}:{s}:{a}:{o}"
                    d = math.dist(tile, (xx, yy))
                    if addr not in best or (d, (yy, xx)) < (best[addr][0], (best[addr][1][1], best[addr][1][0])):
                        best[addr] = (d, (xx, yy))
            hit = tuple(sorted(((a, d, t) for a, (d, t) in best.items()), key=lambda x: (x[1], x[0])))
            self._objects_cache[key] = hit
        return hit

    # ------------------------------------------------------------------ perception
    def learn_space(self, spatial: SpatialMemory, tile: Tile, r: int) -> int:
        learned = 0
        for s, a, o in self.visible_places(tile, r):
            if spatial.learn(self.world.world, s, a, o):
                learned += 1
        return learned

    def perceive(
        self,
        observer: AgentView,
        vision_r: int,
        att_bandwidth: int,
        agents: dict[str, AgentView],
        world_state: WorldState,
        now: datetime,
        spatial: SpatialMemory | None = None,
        learn_space: bool = True,
    ) -> PerceptionResult:
        tile = observer.tile
        here = self.arena_key(tile)
        res = PerceptionResult(observer.agent_id, tile, here)
        if spatial is not None and learn_space:
            res.learned_places = self.learn_space(spatial, tile, vision_r)
        events: list[Percept] = []
        s, p, o = observer.spo
        events.append(Percept("self", s, p, o, observer.description, tile, 0.0, agent_id=observer.agent_id, address=observer.address))
        for other in agents.values():
            if other.agent_id == observer.agent_id or not self.in_square(tile, other.tile, vision_r):
                continue
            if self.arena_key(other.tile) != here:
                continue
            s, p, o = other.spo
            events.append(Percept("agent", s, p, o, other.description, other.tile, math.dist(tile, other.tile), agent_id=other.agent_id, address=other.address))
        for addr, d, otile in self.visible_objects(tile, vision_r):
            state = world_state.state_of(addr)
            name = addr.rsplit(":", 1)[-1]
            events.append(Percept("object", addr, "is", state, f"{name} is {state}", otile, d, address=addr, state=state))
        for ev in world_state.active_ambient(now):
            if self.in_square(tile, ev.tile, vision_r) and self.arena_key(ev.tile) == here:
                events.append(
                    Percept("ambient", ev.subject, ev.predicate, ev.object, ev.description, ev.tile, math.dist(tile, ev.tile), address=f"ambient:{ev.id}")
                )
        res.candidates = len(events)
        events.sort(key=lambda e: (e.distance, _KIND_RANK[e.kind], e.subject))
        res.percepts = events[: max(0, att_bandwidth)]
        if spatial is not None:
            for e in res.percepts:
                if e.kind == "object" and e.address:
                    spatial.saw_state(e.address, e.state or IDLE, now)
        return res
