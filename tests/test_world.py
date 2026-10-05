"""World tree, pathfinding, perception, spatial memory, constraints and object state (spec J-1 … J-8)."""

from __future__ import annotations

from datetime import datetime

import pytest

from generative_agents.config import repo_path
from generative_agents.db import Database
from generative_agents.schemas import AgentIdentity
from generative_agents.world.constraints import Constraints
from generative_agents.world.hierarchy import WorldMap
from generative_agents.world.navigation import Navigator
from generative_agents.world.perception import AgentView, Perceiver
from generative_agents.world.spatial import SpatialMemory
from generative_agents.world.state import AmbientEvent, WorldState

MAP = repo_path("scenarios/smallville_n25/map/the_ville.json")
CONSTRAINTS = repo_path("scenarios/smallville_n25/constraints.yaml")
NOW = datetime(2023, 2, 13, 9, 0)


@pytest.fixture(scope="module")
def world() -> WorldMap:
    return WorldMap.load(MAP)


def ident(aid: str, first: str, last: str) -> AgentIdentity:
    return AgentIdentity(
        id=aid, name=f"{first} {last}", first_name=first, last_name=last, age=30, innate="", learned="", currently="", lifestyle="", living_area="the Ville"
    )


def test_world_tree_matches_released_matrices(world):
    d = world.describe()
    assert (d["width"], d["height"]) == (140, 100)
    assert d["sectors"] == 19 and d["arenas"] == 63
    assert world.exists("the Ville:Hobbs Cafe:cafe:behind the cafe counter")
    assert world.address_at(72, 14) == "the Ville:Isabella Rodriguez's apartment:main room:bed"
    assert world.address_at(72, 14, level="arena") == "the Ville:Isabella Rodriguez's apartment:main room"
    assert "Klaus Mueller's room" in world.tree["the Ville"]["Dorm for Oak Hill College"]


def test_bfs_path_is_shortest_contiguous_and_walkable(world):
    nav = Navigator(world)
    start = (72, 14)
    goal = world.walkable_tiles_for("the Ville:Hobbs Cafe:cafe:behind the cafe counter")[0]
    path = nav.path(start, goal)
    assert path is not None and path[-1] == goal
    assert len(path) == nav.distance(start, goal)
    prev = start
    for t in path:
        assert world.walkable(*t)
        assert abs(t[0] - prev[0]) + abs(t[1] - prev[1]) == 1  # 4-neighbour, one tile per step
        prev = t
    assert nav.path(start, start) == []
    wall = next((x, y) for y in range(world.height) for x in range(world.width) if world.collision[y, x])
    assert nav.path(start, wall) is None
    nav.path(start, goal)
    assert nav.stats["cache_hits"] >= 1  # distance field reused


def test_nearest_prefers_free_tiles_and_is_deterministic(world):
    nav = Navigator(world)
    tiles = world.walkable_tiles_for("the Ville:Hobbs Cafe:cafe:cafe customer seating")
    here = (72, 19)
    best, d = nav.nearest(here, tiles)
    best2, _ = nav.nearest(here, tiles, avoid={best})
    assert best2 != best
    assert nav.nearest(here, [best], avoid={best})[0] == best  # occupied is still better than nothing
    assert nav.nearest(here, tiles) == (best, d)


def test_meeting_tile_is_on_the_path_between_agents(world):
    nav = Navigator(world)
    a, b = (72, 19), (80, 21)
    m = nav.meeting_tile(a, b)
    assert m is not None and world.walkable(*m)
    assert nav.distance(a, m) + nav.distance(m, b) == nav.distance(a, b)


def test_perception_square_same_arena_bandwidth_and_self(world):
    p = Perceiver(world)
    ws = WorldState(Database(None))
    me = AgentView("a", "Ann Lee", (72, 19), activity="drinking coffee")
    near = AgentView("b", "Bob Ray", (80, 21), activity="reading")
    far_x = AgentView("c", "Cat Moe", (72 + 9, 19), activity="cleaning")  # outside the 8-tile square
    other_arena = AgentView("d", "Dan Fox", (72, 14), activity="sleeping")  # apartment upstairs
    views = {v.agent_id: v for v in (me, near, far_x, other_arena)}
    res = p.perceive(me, 8, 8, views, ws, NOW)
    kinds = [x.kind for x in res.percepts]
    subjects = {x.subject for x in res.percepts}
    assert kinds[0] == "self" and res.percepts[0].description == "Ann Lee is drinking coffee"
    assert "Bob Ray" in subjects and "Cat Moe" not in subjects and "Dan Fox" not in subjects
    assert len(res.percepts) <= 8 and res.candidates >= len(res.percepts)
    assert all(a.distance <= b.distance for a, b in zip(res.percepts, res.percepts[1:], strict=False))
    objs = [x for x in res.percepts if x.kind == "object"]
    assert objs and all(x.description.endswith("is idle") for x in objs)
    narrow = p.perceive(me, 8, 2, views, ws, NOW)
    assert len(narrow.percepts) == 2


def test_agents_on_the_street_see_each_other(world):
    p = Perceiver(world)
    ws = WorldState(Database(None))
    a = AgentView("a", "Ann Lee", (72, 28))
    b = AgentView("b", "Bob Ray", (76, 28), activity="walking")
    assert p.arena_key(a.tile) == ("", "")
    res = p.perceive(a, 8, 8, {"a": a, "b": b}, ws, NOW)
    assert any(x.subject == "Bob Ray" for x in res.percepts)


def test_spatial_memory_grows_only_from_what_is_seen(world):
    p = Perceiver(world)
    mem = SpatialMemory("a", {"the Ville": {"Hobbs Cafe": {"cafe": ["piano"]}}})
    assert not mem.knows("the Ville:Isabella Rodriguez's apartment")
    assert not mem.knows("the Ville:Johnson Park")
    learned = p.learn_space(mem, (72, 19), 8)
    assert learned > 0
    assert mem.knows("the Ville:Hobbs Cafe:cafe:behind the cafe counter")
    assert mem.knows("the Ville:Isabella Rodriguez's apartment")  # visible through the square, as in the released code
    assert not mem.knows("the Ville:Johnson Park")  # far away: still unknown
    again = SpatialMemory.from_json("a", mem.to_json())
    assert again.counts() == mem.counts()


def test_object_state_overlay_lasting_and_release():
    ws = WorldState(Database(None))
    stove = "the Ville:Dorm for Oak Hill College:kitchen:cooking area"
    assert ws.state_of(stove) == "idle"
    ws.set_lasting(stove, "burning", NOW, "intervention")
    ws.use(stove, "klaus", "being used to cook", NOW)
    assert ws.state_of(stove) == "being used to cook"
    ws.release("klaus")
    assert ws.state_of(stove) == "burning"  # interventions outlive the action
    ws.set_lasting(stove, "turned off", NOW, "agent")
    assert ws.state_of(stove) == "turned off"
    ws.add_ambient(AmbientEvent(id="fire1", tile=(76, 28), subject="fire", object="burning", description="a fire is burning on the street", started_at=NOW))
    ws.flush()
    again = WorldState(ws.db)
    assert again.state_of(stove) == "turned off" and [e.id for e in again.active_ambient(NOW)] == ["fire1"]


def test_strict_v1_constraints():
    c = Constraints.load(CONSTRAINTS, "strict-v1")
    sam = ident("sam_moore", "Sam", "Moore")
    carmen = ident("carmen_ortiz", "Carmen", "Ortiz")
    evening = datetime(2023, 2, 13, 18, 0)
    v = c.check(sam, "the Ville:Harvey Oak Supply Store:supply store", evening)
    assert not v.allowed and v.rule == "closed" and "08:00" in v.message
    assert c.check(carmen, "the Ville:Harvey Oak Supply Store", evening).allowed  # staff
    assert c.check(sam, "the Ville:Harvey Oak Supply Store", NOW).allowed
    klaus = ident("klaus_mueller", "Klaus", "Mueller")
    room = "the Ville:Dorm for Oak Hill College:Klaus Mueller's room"
    assert c.check(klaus, room, NOW).allowed
    v = c.check(sam, room, NOW)
    assert not v.allowed and v.rule == "private"
    john = ident("john_lin", "John", "Lin")
    assert c.check(john, "the Ville:Lin family's house:Mei and John Lin's bedroom", NOW).allowed
    bath = "the Ville:Dorm for Oak Hill College:man's bathroom"
    occ = {bath: {"klaus_mueller"}}
    v = c.check(sam, bath, NOW, occ)
    assert not v.allowed and v.rule == "occupied" and v.retry_after_min
    assert c.check(klaus, bath, NOW, occ).allowed  # the occupant himself
    assert c.check(sam, bath, NOW, {}).allowed
    off = Constraints.load(CONSTRAINTS, "none")
    assert off.check(sam, room, evening).allowed and off.check(sam, bath, NOW, occ).allowed
