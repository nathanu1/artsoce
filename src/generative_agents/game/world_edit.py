"""Placed items as real world objects, and placement validation (game layer).

The scenario's map is never written to disk. ``WorldEditor`` keeps a pristine copy of the
loaded layers and rebuilds the in-memory world from it plus the list of placed items, so a
rollback, a resume or a replay always reconstructs the same world from the same item list.

A placed item becomes an object address ``world:sector:room:name`` on its tiles. Residents
perceive it like any map object, learn it into their own spatial memory when they see it, and
may choose it for activities. Blocking items (fences, hedges, fountains) also change the
collision grid; they may not cut any walkable tile off from the rest of the town.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..world.hierarchy import WorldMap
from ..world.navigation import Navigator
from ..world.perception import Perceiver
from .content import CatalogItem, GameContent, Zone

Tile = tuple[int, int]


def apply_zones(world: WorldMap, zones: list[Zone]) -> dict[str, int]:
    """Turn open street tiles inside each zone into a named place (before any item is placed)."""

    added: dict[str, int] = {}
    for z in zones:
        sectors, arenas = world.legend["sector"], world.legend["arena"]
        if z.sector not in sectors:
            sectors.append(z.sector)
        if z.arena not in arenas:
            arenas.append(z.arena)
        si, ai = sectors.index(z.sector), arenas.index(z.arena)
        x0, y0, x1, y1 = z.rect
        n = 0
        for y in range(max(0, y0), min(world.height - 1, y1) + 1):
            for x in range(max(0, x0), min(world.width - 1, x1) + 1):
                if not world.collision[y, x] and world.sector[y, x] == 0:
                    world.sector[y, x] = si
                    world.arena[y, x] = ai
                    n += 1
        added[z.id] = n
    world.__dict__.pop("sector_boxes", None)
    world._build_indexes()
    return added


@dataclass
class PlacedItem:
    id: str
    catalog_id: str
    name: str
    x: int
    y: int
    rot: int
    paint: str | None
    address: str
    tiles: list[Tile]
    blocks: bool
    placed_at: str | None = None
    step: int | None = None

    def to_json(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d["tiles"] = [list(t) for t in self.tiles]
        return d

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> PlacedItem:
        d = dict(d)
        d["tiles"] = [tuple(t) for t in d["tiles"]]
        return cls(**d)


@dataclass
class Draft:
    """One item in a build request: a new item, or a move/repaint of ``item_id``."""

    catalog_id: str
    x: int
    y: int
    rot: int = 0
    paint: str | None = None
    item_id: str | None = None


@dataclass
class Verdict:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    tiles: list[Tile] = field(default_factory=list)
    arena: str | None = None
    outdoor: bool | None = None

    def to_json(self) -> dict[str, Any]:
        return {"ok": self.ok, "reasons": self.reasons, "tiles": [list(t) for t in self.tiles], "arena": self.arena, "outdoor": self.outdoor}


class WorldEditor:
    def __init__(self, world: WorldMap, nav: Navigator, perceiver: Perceiver, content: GameContent):
        self.world = world
        self.nav = nav
        self.perceiver = perceiver
        self.content = content
        self._base_object = world.object.copy()
        self._base_collision = world.collision.copy()
        self._base_legend = list(world.legend["object"])
        self._outdoor_words = [w.lower() for w in content.outdoor_keywords]
        ground_words = [w.lower() for w in content.ground_objects]
        # Map objects on each tile: solid ones (furniture) block placement; ground cover
        # (gardens) can take items as long as enough of it is left.
        self._solid_tiles: set[Tile] = set()
        self._ground_at: dict[Tile, str] = {}
        self._ground_size: dict[str, int] = {}
        for y, x in zip(*np.nonzero(self._base_object), strict=False):
            tile = (int(x), int(y))
            name = self._base_legend[int(self._base_object[y, x])]
            address = world.address_at(*tile)
            if any(gw in name.lower() for gw in ground_words) and address:
                self._ground_at[tile] = address
                self._ground_size[address] = self._ground_size.get(address, 0) + 1
            else:
                self._solid_tiles.add(tile)

    # ------------------------------------------------------------------ geometry
    def footprint(self, item: CatalogItem, x: int, y: int, rot: int) -> list[Tile]:
        w, h = item.size(rot)
        return [(x + dx, y + dy) for dy in range(h) for dx in range(w)]

    def is_outdoor(self, arena_address: str) -> bool:
        name = arena_address.split(":")[2].lower() if arena_address.count(":") >= 2 else ""
        return any(w in name.split() or w == name for w in self._outdoor_words)

    def arena_of(self, tile: Tile) -> str | None:
        return self.world.arena_at(*tile)

    # ------------------------------------------------------------------ world rebuild
    def apply(self, items: list[PlacedItem]) -> None:
        """Rebuild the in-memory world from the base map plus ``items`` (in order)."""

        w = self.world
        w.object[:, :] = self._base_object
        w.collision[:, :] = self._base_collision
        legend = list(self._base_legend)
        index = {name: i for i, name in enumerate(legend) if name}
        for it in items:
            if it.name not in index:
                index[it.name] = len(legend)
                legend.append(it.name)
            for x, y in it.tiles:
                w.object[y, x] = index[it.name]
                if it.blocks:
                    w.collision[y, x] = True
        w.legend["object"] = legend
        w._build_indexes()
        self.nav._walk = [not bool(v) for v in w.collision.reshape(-1).tolist()]
        self.nav._cache.clear()
        self.perceiver._square_cache.clear()
        self.perceiver._objects_cache.clear()

    def unique_name(self, base: str, arena: str, taken: set[str]) -> str:
        """``base``, or ``base 2``, ``base 3``… so addresses stay unique inside a room."""

        existing = {a.rsplit(":", 1)[-1] for a in self.world.object_addresses_in(arena)} | taken
        if base not in existing:
            return base
        n = 2
        while f"{base} {n}" in existing:
            n += 1
        return f"{base} {n}"

    # ------------------------------------------------------------------ validation
    def validate(
        self,
        drafts: list[Draft],
        *,
        placed: list[PlacedItem],
        removing: set[str] = frozenset(),
        agents: dict[str, dict[str, Any]] | None = None,
        level: int = 5,
    ) -> list[Verdict]:
        """Check a whole build batch against the current world.

        ``placed``: items already in the world; ``removing``: ids deleted in this batch;
        ``agents``: ``{id: {"tile": (x, y), "path": [...], "target": address, "using": address}}``.
        Items being moved (``Draft.item_id``) are checked as if lifted first.
        """

        agents = agents or {}
        moving = {d.item_id for d in drafts if d.item_id}
        staying = [p for p in placed if p.id not in removing and p.id not in moving]
        busy_items = {p.id for p in placed for a in agents.values() if p.address in (a.get("target"), a.get("using"))}
        occupied: dict[Tile, str] = {}
        for p in staying:
            for t in p.tiles:
                occupied[t] = f"the {p.name}"
        agent_tiles = {tuple(a["tile"]): aid for aid, a in agents.items() if a.get("tile")}
        path_tiles = {tuple(t) for a in agents.values() for t in (a.get("path") or [])}
        verdicts: list[Verdict] = []
        new_blocked: set[Tile] = set()
        for d in drafts:
            v = Verdict(ok=True)
            try:
                item = self.content.item(d.catalog_id)
            except KeyError:
                verdicts.append(Verdict(ok=False, reasons=[f"unknown item {d.catalog_id}"]))
                continue
            if item.unlock > level:
                v.reasons.append(f"unlocks at Town Pulse level {item.unlock}")
            if d.item_id and d.item_id in busy_items:
                v.reasons.append("someone is using it right now")
            if d.paint is not None:
                try:
                    self.content.paint(d.paint)
                except KeyError:
                    v.reasons.append(f"unknown paint {d.paint}")
            tiles = self.footprint(item, d.x, d.y, d.rot)
            v.tiles = tiles
            if not all(self.world.in_bounds(*t) for t in tiles):
                v.reasons.append("goes off the edge of the map")
                v.ok = False
                verdicts.append(v)
                continue
            arenas = {self.arena_of(t) for t in tiles}
            if None in arenas:
                v.reasons.append("needs to be inside a room, garden or park (not on the street)")
            elif len(arenas) > 1:
                v.reasons.append("must sit inside a single room or garden")
            else:
                v.arena = next(iter(arenas))
                v.outdoor = self.is_outdoor(v.arena)
                if item.placement == "indoor" and v.outdoor:
                    v.reasons.append("belongs indoors")
                if item.placement == "outdoor" and not v.outdoor:
                    v.reasons.append("belongs outdoors, in a garden or park")
            if any(bool(self._base_collision[y, x]) for x, y in tiles):
                v.reasons.append("a wall or obstacle is in the way")
            if any(t in self._solid_tiles for t in tiles):
                v.reasons.append("overlaps something that is already there")
            for ground, used in self._ground_use(tiles, staying, occupied).items():
                if self._ground_size[ground] - used < self.content.ground_min_tiles:
                    v.reasons.append(f"would cover too much of the {ground.rsplit(':', 1)[-1]}")
            clash = sorted({occupied[t] for t in tiles if t in occupied})
            if clash:
                v.reasons.append(f"overlaps {', '.join(clash)}")
            if item.blocks:
                on_agent = sorted({agent_tiles[t] for t in tiles if t in agent_tiles})
                if on_agent:
                    v.reasons.append("someone is standing there")
                elif any(t in path_tiles for t in tiles):
                    v.reasons.append("someone is walking through here")
            if not v.reasons:
                for t in tiles:
                    occupied[t] = f"the new {item.name}"
                if item.blocks:
                    new_blocked.update(tiles)
            v.ok = not v.reasons
            verdicts.append(v)
        if new_blocked and all(v.ok for v in verdicts):
            lost = self._cut_off(new_blocked, staying)
            if lost:
                for v, d in zip(verdicts, drafts, strict=True):
                    if self.content.item(d.catalog_id).blocks:
                        v.ok = False
                        v.reasons.append(f"would cut off {lost} walkable tiles from the rest of town")
        return verdicts

    def _ground_use(self, tiles: list[Tile], staying: list[PlacedItem], occupied: dict[Tile, str]) -> dict[str, int]:
        """Ground-cover tiles already covered (by items and earlier drafts) plus ``tiles``."""

        covered = {t for p in staying for t in p.tiles} | set(occupied) | set(tiles)
        out: dict[str, int] = {}
        for t in covered:
            g = self._ground_at.get(t)
            if g and any(self._ground_at.get(x) == g for x in tiles):
                out[g] = out.get(g, 0) + 1
        return out

    def _cut_off(self, new_blocked: set[Tile], staying: list[PlacedItem]) -> int:
        """Walkable tiles that blocking ``new_blocked`` would separate from their own area.

        Every connected walkable area must stay connected once the new tiles are blocked; the
        count is how many tiles end up outside the largest remaining piece of their area.
        """

        blocked = self._base_collision.copy()
        for p in staying:
            if p.blocks:
                for x, y in p.tiles:
                    blocked[y, x] = True
        before = self._labels(blocked)
        for x, y in new_blocked:
            blocked[y, x] = True
        after = self._labels(blocked)
        pieces: dict[int, dict[int, int]] = {}
        for (y, x), lb in np.ndenumerate(before):
            if lb < 0 or after[y, x] < 0:
                continue
            counts = pieces.setdefault(int(lb), {})
            counts[int(after[y, x])] = counts.get(int(after[y, x]), 0) + 1
        return sum(sum(c.values()) - max(c.values()) for c in pieces.values() if len(c) > 1)

    @staticmethod
    def _labels(blocked: np.ndarray) -> np.ndarray:
        """Connected-area label per walkable tile (4-neighbour), -1 for blocked tiles."""

        h, w = blocked.shape
        labels = np.full((h, w), -1, dtype=np.int32)
        flat_blocked = blocked.reshape(-1).tolist()
        flat = labels.reshape(-1)
        current = 0
        for start in range(w * h):
            if flat_blocked[start] or flat[start] >= 0:
                continue
            flat[start] = current
            q = deque([start])
            while q:
                i = q.popleft()
                x, y = i % w, i // w
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h:
                        j = ny * w + nx
                        if flat[j] < 0 and not flat_blocked[j]:
                            flat[j] = current
                            q.append(j)
            current += 1
        return labels
