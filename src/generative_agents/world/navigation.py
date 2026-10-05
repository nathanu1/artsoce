"""Pathfinding on the collision grid (paper §5.1; spec J-3).

The released ``path_finder.py`` runs a breadth-first search over 4-neighbour moves and agents
advance one tile per step. We do the same, with two engineering choices recorded in the
reproduction spec (D-9):

* the target tile is the reachable tile of the address nearest to the agent, preferring
  tiles no other agent stands on (the released code samples up to four random tiles and
  picks the closest of those), and ties break on ``(distance, y, x)`` so runs are
  deterministic;
* BFS distance fields are cached per start tile (LRU), so repeated plans from the same
  tile cost nothing.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from collections.abc import Iterable

from .hierarchy import WorldMap

Tile = tuple[int, int]
NEIGHBOURS: tuple[tuple[int, int], ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))


class Navigator:
    def __init__(self, world: WorldMap, cache_size: int = 512):
        self.world = world
        self.width = world.width
        self.height = world.height
        self._walk: list[bool] = [not bool(v) for v in world.collision.reshape(-1).tolist()]
        self._cache: OrderedDict[Tile, list[int]] = OrderedDict()
        self.cache_size = cache_size
        self.stats = {"bfs": 0, "cache_hits": 0}

    def walkable(self, tile: Tile) -> bool:
        x, y = tile
        return 0 <= x < self.width and 0 <= y < self.height and self._walk[y * self.width + x]

    def distances_from(self, start: Tile) -> list[int]:
        """Flat BFS distance field from ``start`` (``-1`` = unreachable)."""

        key = (int(start[0]), int(start[1]))
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            self.stats["cache_hits"] += 1
            return hit
        w, h, walk = self.width, self.height, self._walk
        dist = [-1] * (w * h)
        sx, sy = key
        dist[sy * w + sx] = 0
        queue = deque([key])
        while queue:
            x, y = queue.popleft()
            d = dist[y * w + x] + 1
            for dx, dy in NEIGHBOURS:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    i = ny * w + nx
                    if dist[i] < 0 and walk[i]:
                        dist[i] = d
                        queue.append((nx, ny))
        self.stats["bfs"] += 1
        self._cache[key] = dist
        if len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)
        return dist

    def distance(self, start: Tile, goal: Tile) -> int:
        return self.distances_from(start)[goal[1] * self.width + goal[0]]

    def path(self, start: Tile, goal: Tile) -> list[Tile] | None:
        """Tiles to walk from ``start`` (exclusive) to ``goal`` (inclusive); None if unreachable."""

        start = (int(start[0]), int(start[1]))
        goal = (int(goal[0]), int(goal[1]))
        if start == goal:
            return []
        dist = self.distances_from(start)
        w = self.width
        d = dist[goal[1] * w + goal[0]]
        if d < 0:
            return None
        out = [goal]
        x, y = goal
        while d > 1:
            for dx, dy in NEIGHBOURS:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < self.height and dist[ny * w + nx] == d - 1:
                    x, y, d = nx, ny, d - 1
                    out.append((x, y))
                    break
            else:  # pragma: no cover - BFS fields always have a predecessor
                return None
        out.reverse()
        return out

    def nearest(self, start: Tile, candidates: Iterable[Tile], avoid: set[Tile] | frozenset[Tile] = frozenset()) -> tuple[Tile, int] | None:
        """Closest reachable candidate, preferring tiles not in ``avoid``."""

        dist = self.distances_from(start)
        w = self.width
        free: list[tuple[int, int, int]] = []
        taken: list[tuple[int, int, int]] = []
        for x, y in candidates:
            d = dist[y * w + x]
            if d < 0:
                continue
            (taken if (x, y) in avoid else free).append((d, y, x))
        pool = free or taken
        if not pool:
            return None
        d, y, x = min(pool)
        return (x, y), d

    def meeting_tile(self, a: Tile, b: Tile) -> Tile | None:
        """Midpoint of the shortest path between two agents (released execute.py ``<persona>``)."""

        p = self.path(a, b)
        if p is None:
            return None
        full = [tuple(a), *p]
        return full[(len(full) - 1) // 2]
