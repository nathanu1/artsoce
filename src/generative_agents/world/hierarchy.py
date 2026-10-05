"""The authoritative world tree: world → sector → arena → object (paper §5.1, Fig. 2; spec J-1, J-8).

Tile layers come from the official ``the_ville`` matrices (converted by
``scenario.importer``). An address is ``world:sector:arena:object`` built from the tile's
layers, exactly as ``maze.py`` builds them; arena and object names are only unique inside
their parents.
"""

from __future__ import annotations

import json
from collections import defaultdict
from functools import cached_property
from pathlib import Path
from typing import Any

import numpy as np


def _decode(rle: list[list[int]], size: int) -> np.ndarray:
    out = np.empty(size, dtype=np.int32)
    i = 0
    for value, count in rle:
        out[i : i + count] = value
        i += count
    if i != size:
        raise ValueError(f"layer length {i} != {size}")
    return out


class WorldMap:
    def __init__(self, data: dict[str, Any]):
        self.world: str = data["world"]
        self.width: int = int(data["width"])
        self.height: int = int(data["height"])
        self.tile_px: int = int(data.get("tile_px", 32))
        self.source = data.get("source", {})
        size = self.width * self.height
        L = data["layers"]
        self.collision = _decode(L["collision"], size).reshape(self.height, self.width).astype(bool)
        self.sector = _decode(L["sector"], size).reshape(self.height, self.width)
        self.arena = _decode(L["arena"], size).reshape(self.height, self.width)
        self.object = _decode(L["object"], size).reshape(self.height, self.width)
        self.spawn = _decode(L["spawn"], size).reshape(self.height, self.width)
        self.legend = data["legend"]
        self._build_indexes()

    @classmethod
    def load(cls, path: str | Path) -> WorldMap:
        return cls(json.loads(Path(path).read_text()))

    # ------------------------------------------------------------------ indexes
    def _build_indexes(self) -> None:
        self.address_tiles: dict[str, list[tuple[int, int]]] = defaultdict(list)
        tree: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for y in range(self.height):
            for x in range(self.width):
                s = self.legend["sector"][self.sector[y, x]]
                if not s:
                    continue
                sec_addr = f"{self.world}:{s}"
                self.address_tiles[sec_addr].append((x, y))
                a = self.legend["arena"][self.arena[y, x]]
                if not a:
                    tree[s]  # noqa: B018 - registers the sector
                    continue
                ar_addr = f"{sec_addr}:{a}"
                self.address_tiles[ar_addr].append((x, y))
                tree[s][a]  # noqa: B018
                o = self.legend["object"][self.object[y, x]]
                if o:
                    self.address_tiles[f"{ar_addr}:{o}"].append((x, y))
                    tree[s][a].add(o)
        self.address_tiles = dict(self.address_tiles)
        self._tree = {s: {a: sorted(objs) for a, objs in sorted(arenas.items())} for s, arenas in sorted(tree.items())}

    @property
    def tree(self) -> dict[str, Any]:
        return {self.world: self._tree}

    # ------------------------------------------------------------------ tile queries
    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def walkable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and not self.collision[y, x]

    def names_at(self, x: int, y: int) -> tuple[str, str, str]:
        return (
            self.legend["sector"][self.sector[y, x]],
            self.legend["arena"][self.arena[y, x]],
            self.legend["object"][self.object[y, x]],
        )

    def address_at(self, x: int, y: int, level: str = "object") -> str | None:
        s, a, o = self.names_at(x, y)
        if not s:
            return None
        parts = [self.world, s]
        if level == "sector":
            return ":".join(parts)
        if not a:
            return ":".join(parts) if level != "arena" else None
        parts.append(a)
        if level == "arena":
            return ":".join(parts)
        if o:
            parts.append(o)
        return ":".join(parts)

    def arena_at(self, x: int, y: int) -> str | None:
        return self.address_at(x, y, "arena")

    def sector_at(self, x: int, y: int) -> str | None:
        return self.address_at(x, y, "sector")

    def object_addresses_in(self, arena_address: str) -> list[str]:
        prefix = arena_address + ":"
        return sorted(a for a in self.address_tiles if a.startswith(prefix) and a.count(":") == 3)

    def tiles_for(self, address: str) -> list[tuple[int, int]]:
        return self.address_tiles.get(address, [])

    def exists(self, address: str) -> bool:
        return address in self.address_tiles

    def walkable_tiles_for(self, address: str) -> list[tuple[int, int]]:
        return [t for t in self.tiles_for(address) if self.walkable(*t)]

    @cached_property
    def sector_boxes(self) -> dict[str, dict[str, int]]:
        """Bounding boxes per sector (for the viewer)."""

        boxes: dict[str, dict[str, int]] = {}
        for addr, tiles in self.address_tiles.items():
            if addr.count(":") != 1:
                continue
            xs = [t[0] for t in tiles]
            ys = [t[1] for t in tiles]
            boxes[addr] = {"x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys), "tiles": len(tiles)}
        return boxes

    def describe(self) -> dict[str, Any]:
        return {
            "world": self.world,
            "width": self.width,
            "height": self.height,
            "sectors": len(self._tree),
            "arenas": sum(len(a) for a in self._tree.values()),
            "objects": sum(1 for a in self.address_tiles if a.count(":") == 3),
            "source": self.source,
        }


def tree_addresses(tree: dict[str, Any]) -> set[str]:
    """All sector, arena and object addresses in a nested spatial tree."""

    out: set[str] = set()
    for world, sectors in tree.items():
        for sector, arenas in (sectors or {}).items():
            out.add(f"{world}:{sector}")
            for arena, objects in (arenas or {}).items():
                out.add(f"{world}:{sector}:{arena}")
                for obj in objects or []:
                    out.add(f"{world}:{sector}:{arena}:{obj}")
    return out
