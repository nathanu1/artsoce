"""The town game layer (an extension): content, affinity, building, actions, information scope."""

from __future__ import annotations

import json

import pytest

from generative_agents.game.affinity import Affinity
from generative_agents.game.content import GameContent, load_content
from generative_agents.game.world_edit import Draft, PlacedItem, WorldEditor
from generative_agents.providers.embeddings import MockHashEmbedding
from generative_agents.providers.mock import MockLLM
from generative_agents.schemas import MemoryOrigin
from generative_agents.simulation.engine import Simulation
from generative_agents.world.hierarchy import WorldMap
from generative_agents.world.navigation import Navigator
from generative_agents.world.perception import AgentView, Perceiver
from generative_agents.world.state import WorldState
from helpers import sim_config

TRIO = ["isabella_rodriguez", "maria_lopez", "klaus_mueller"]
CONTENT = load_content()


def game_sim(tmp_path, name="g", start="2023-02-13T10:00:00", end="2023-02-13T13:00:00", extra=()):
    cfg = sim_config(TRIO, start=start, end=end, extra=("game.enabled=true", *extra))
    return Simulation(cfg, tmp_path / name, provider=MockLLM(seed=5), embedding_provider=MockHashEmbedding(128))


def events_of(sim, kind):
    return [e for e in sim.game.store.events() if e["kind"] == kind]


# ---------------------------------------------------------------------- content and affinity
def test_content_needs_exactly_six_consistent_themes():
    data = json.loads(CONTENT.model_dump_json())
    assert len(data["themes"]) == 6 and len(data["items"]) >= 30
    bad = json.loads(CONTENT.model_dump_json())
    bad["themes"] = bad["themes"][:5]
    with pytest.raises(ValueError, match="exactly six"):
        GameContent.model_validate(bad)
    bad = json.loads(CONTENT.model_dump_json())
    bad["templates"][0]["parts"][0]["item"] = "flying_carpet"
    with pytest.raises(ValueError, match="unknown item"):
        GameContent.model_validate(bad)
    bad = json.loads(CONTENT.model_dump_json())
    bad["levels"][2]["points"] = 10
    with pytest.raises(ValueError, match="Town Pulse"):
        GameContent.model_validate(bad)


def test_affinities_come_from_identity_activities_and_places(tmp_path):
    aff = Affinity(CONTENT)
    sim = game_sim(tmp_path)
    loves = {aid: aff.resident(sim.identities[aid])["loves"] for aid in TRIO}
    assert loves["isabella_rodriguez"] == ["cozy", "spark"]  # cafe owner, party host
    assert loves["klaus_mueller"][0] == "lore"  # sociology student writing a paper
    assert aff.classify("Isabella Rodriguez is planning a Valentine's Day party") == "spark"
    assert aff.search_theme("the Ville:Oak Hill College:library:bookshelf") == "lore"
    assert aff.search_theme("the Ville:Moore family's house:bathroom:toilet") is None  # building words do not count
    assert aff.top(aff.place_scores("the Ville:Johnson Park:park:park garden")) == "bloom"


# ---------------------------------------------------------------------- placement on a tiny map
def tiny_world() -> WorldMap:
    rows = [
        "#######",
        "#..#..#",
        "#.....#",
        "#..#..#",
        "#######",
    ]
    h, w = len(rows), len(rows[0])

    def rle(values):
        out = []
        for v in values:
            if out and out[-1][0] == v:
                out[-1][1] += 1
            else:
                out.append([v, 1])
        return out

    flat = "".join(rows)
    return WorldMap(
        {
            "world": "w",
            "width": w,
            "height": h,
            "legend": {"sector": ["", "Town"], "arena": ["", "garden"], "object": ["", "rock"], "spawn": [""]},
            "layers": {
                "collision": rle([1 if c == "#" else 0 for c in flat]),
                "sector": rle([1] * (w * h)),
                "arena": rle([1] * (w * h)),
                "object": rle([1 if (i % w, i // w) == (5, 1) else 0 for i in range(w * h)]),
                "spawn": rle([0] * (w * h)),
            },
        }
    )


def editor_for(world):
    nav, per = Navigator(world), Perceiver(world)
    return WorldEditor(world, nav, per, CONTENT), nav, per


def test_placement_rules_name_every_problem():
    world = tiny_world()
    ed, _, _ = editor_for(world)

    def check(cid, x, y, rot=0, level=5, **kw):
        return ed.validate([Draft(cid, x, y, rot)], placed=kw.get("placed", []), agents=kw.get("agents"), level=level)[0]

    assert check("flower_planter", 1, 1).ok
    assert "belongs indoors" in check("armchair", 1, 1).reasons
    assert "a wall or obstacle is in the way" in check("flower_planter", 0, 0).reasons
    assert "overlaps something that is already there" in check("flower_planter", 5, 1).reasons
    assert "goes off the edge of the map" in check("bench", 6, 2).reasons
    assert check("bench", 1, 1, rot=1).tiles == [(1, 1), (1, 2)]  # rotation swaps the footprint
    assert "unlocks at Town Pulse level 4" in check("town_fountain", 1, 1, level=1).reasons
    planter = PlacedItem("i0001", "flower_planter", "flower planter", 1, 2, 0, None, "w:Town:garden:flower planter", [(1, 2)], False)
    assert "overlaps the flower planter" in check("bench", 1, 2, placed=[planter]).reasons
    assert "someone is standing there" in check("hedge", 2, 2, agents={"a": {"tile": (2, 2), "path": []}}).reasons
    assert "someone is walking through here" in check("hedge", 2, 2, agents={"a": {"tile": (1, 1), "path": [(2, 2)]}}).reasons


def test_blocking_items_may_not_cut_the_town_in_two():
    world = tiny_world()
    ed, _, _ = editor_for(world)
    gap = ed.validate([Draft("hedge", 3, 2)], placed=[], level=5)[0]
    assert not gap.ok and any("cut off" in r for r in gap.reasons)
    corner = ed.validate([Draft("hedge", 1, 1)], placed=[], level=5)[0]
    assert corner.ok


def test_placed_items_become_perceivable_objects_and_block_paths(tmp_path):
    world = tiny_world()
    ed, nav, per = editor_for(world)
    assert nav.distance((4, 1), (4, 3)) == 2
    bench = PlacedItem("i0001", "bench", "bench", 1, 3, 0, None, "w:Town:garden:bench", [(1, 3), (2, 3)], False)
    hedge = PlacedItem("i0002", "hedge", "hedge", 4, 2, 0, None, "w:Town:garden:hedge", [(4, 2)], True)
    ed.apply([bench, hedge])
    assert world.exists("w:Town:garden:bench") and "w:Town:garden:bench" in world.object_addresses_in("w:Town:garden")
    assert nav.distance((4, 1), (4, 3)) == 4  # walks around the hedge
    from generative_agents.db import Database

    seen = per.perceive(AgentView("a", "Ann", (1, 2)), 4, 8, {}, WorldState(Database()), __import__("datetime").datetime(2023, 2, 13, 9))
    assert any(p.kind == "object" and p.description == "bench is idle" for p in seen.percepts)
    ed.apply([])  # removing everything restores the original map exactly
    assert not world.exists("w:Town:garden:bench") and nav.distance((4, 1), (4, 3)) == 2


# ---------------------------------------------------------------------- actions through the engine
def test_chat_gift_and_search_go_through_memory_and_meters(tmp_path):
    sim = game_sim(tmp_path)
    sim.initialize()
    log = sim.game.actions
    log.append(0, "chat", {"agent": "klaus_mueller", "text": "Hi Klaus! What are you working on today?"})
    log.append(0, "gift", {"agent": "isabella_rodriguez", "gift": "party_popper"})
    log.append(0, "search", {"address": "the Ville:Oak Hill College:library:bookshelf"})
    log.append(1, "search", {"address": "the Ville:Oak Hill College:library:bookshelf"})
    log.append(1, "search", {"address": "the Ville:Isabella Rodriguez's apartment:bathroom:toilet"})
    sim.run(max_steps=3)
    chat = events_of(sim, "chat")[0]
    assert chat["reply"] and chat["pulse"] == CONTENT.points["chat"]
    mems = sim.svc.store.for_agent("klaus_mueller")
    said = [m for m in mems if m.speaker_id == "builder"]
    assert said and said[0].origin == MemoryOrigin.STATEMENT and "What are you working on today?" in said[0].description
    assert any(m.origin == MemoryOrigin.OWN_STATEMENT and chat["reply"] in m.description for m in mems)
    gift = events_of(sim, "gift")[0]
    assert gift["loved"] and gift["spent"] == {"melody_note": 1}  # Isabella loves Spark
    assert sim.game.state(sim.clock.now)["friendship"]["isabella_rodriguez"] == CONTENT.friendship["gift_loved"]
    found = events_of(sim, "motif")
    assert len(found) == 1 and found[0]["theme"] == "lore"
    rejected = [e for e in events_of(sim, "rejected") if e["action_kind"] == "search"]
    assert rejected and "already searched" in rejected[0]["reason"]
    assert events_of(sim, "search_empty")[0]["object"] == "toilet"


def test_requests_come_from_known_places_and_complete_through_building(tmp_path):
    sim = game_sim(tmp_path, extra=("game.auto_requests=false",))
    sim.initialize()
    sim.game.actions.append(0, "ask_request", {"agent": "klaus_mueller"})
    sim.run(max_steps=1)
    req = sim.game.state(sim.clock.now)["requests"][0]
    known = sim.spatial.get("klaus_mueller")
    w, sector, arena = req["place_address"].split(":")
    assert arena in known.arenas(w, sector)  # from Klaus's own spatial memory
    assert "bathroom" not in arena and not ("'s" in req["place_label"] and "Klaus" not in req["place_label"])
    assert any(m.origin == MemoryOrigin.OWN_STATEMENT and req["request_line"] in m.description for m in sim.svc.store.for_agent("klaus_mueller"))
    # build something of the requested theme in the requested place
    world = sim.world
    item = next(
        i
        for i in CONTENT.items
        if i.theme == req["theme"] and i.footprint == (1, 1) and i.unlock == 1 and i.placement in ("any", "outdoor" if req["outdoor"] else "indoor")
    )
    tiles = [t for t in world.walkable_tiles_for(req["place_address"]) if not world.names_at(*t)[2]]
    ok_tile = next(t for t in tiles if sim.game.validate_build([{"op": "place", "catalog_id": item.id, "x": t[0], "y": t[1]}])["ok"])
    sim.game.actions.append(sim.clock.step, "build", {"ops": [{"op": "place", "catalog_id": item.id, "x": ok_tile[0], "y": ok_tile[1]}]})
    sim.run(max_steps=1)
    st = sim.game.state(sim.clock.now)
    placed = st["items"][0]
    assert world.exists(placed["address"]) and st["requests"][0]["status"] == "ready"
    sim.game.actions.append(sim.clock.step, "deliver", {"request": req["id"]})
    sim.run(max_steps=1)
    done = sim.game.state(sim.clock.now)
    assert done["requests"][0]["status"] == "fulfilled" and done["stats"]["requests_fulfilled"] == 1
    assert done["pulse"]["level"] == 1 and done["pulse"]["points"] >= CONTENT.points["request_fulfilled"]


def test_build_batches_are_all_or_nothing_and_removal_refunds(tmp_path):
    sim = game_sim(tmp_path, extra=("game.auto_requests=false",))
    sim.initialize()
    plaza = "the Ville:Town Square:plaza"
    tiles = [t for t in sim.world.walkable_tiles_for(plaza) if not sim.world.names_at(*t)[2]]
    a, b = tiles[10], tiles[30]
    sim.run(max_steps=1)  # the starting motifs arrive with the first step
    before = sim.game.theme_counts()
    ops = [{"op": "place", "catalog_id": "flower_planter", "x": a[0], "y": a[1]}, {"op": "place", "catalog_id": "armchair", "x": b[0], "y": b[1]}]
    sim.game.actions.append(sim.clock.step, "build", {"ops": ops})  # the armchair belongs indoors: nothing is built
    sim.game.actions.append(sim.clock.step, "build", {"ops": ops[:1]})
    sim.run(max_steps=1)
    assert events_of(sim, "build_rejected") and len(sim.game.store.items()) == 1
    after = sim.game.theme_counts()
    assert after["bloom"] == before["bloom"] - 1
    item = sim.game.store.items()[0]
    sim.game.actions.append(sim.clock.step, "build", {"ops": [{"op": "remove", "item_id": item.id}]})
    sim.run(max_steps=1)
    assert sim.game.store.items() == [] and not sim.world.exists(item.address) and sim.game.theme_counts()["bloom"] == before["bloom"]


def test_the_town_square_is_a_real_place_and_gardens_take_decor(tmp_path):
    sim = game_sim(tmp_path, extra=("game.auto_requests=false",))
    plaza = "the Ville:Town Square:plaza"
    assert sim.game.zones["town_square"] > 150 and sim.world.exists(plaza)
    assert all(sim.world.names_at(*t)[0] == "Town Square" for t in sim.world.tiles_for(plaza))
    # a resident standing in the square perceives an item placed there
    sim.initialize()
    tile = sim.world.walkable_tiles_for(plaza)[40]
    sim.game.actions.append(0, "build", {"ops": [{"op": "place", "catalog_id": "flower_planter", "x": tile[0], "y": tile[1]}]})
    sim.run(max_steps=1)
    view = AgentView("x", "X", (tile[0] + 1, tile[1]))
    seen = sim.perceiver.perceive(view, 4, 8, {}, sim.world_state, sim.clock.now)
    assert any(p.description == "flower planter is idle" for p in seen.percepts)
    # the park is mostly one "park garden" object: decor may cover it, but not all of it
    park = [t for t in sim.world.tiles_for("the Ville:Johnson Park:park:park garden")]
    ok = sim.game.validate_build([{"op": "place", "catalog_id": "flower_planter", "x": park[0][0], "y": park[0][1]}])
    assert ok["ok"], ok
    ed = sim.game.editor
    size = ed._ground_size["the Ville:Johnson Park:park:park garden"]
    too_many = [Draft("flower_planter", x, y) for x, y in park[: size - CONTENT.ground_min_tiles + 1]]
    verdicts = ed.validate(too_many, placed=sim.game.store.items(), level=5)
    assert not verdicts[-1].ok and "would cover too much of the park garden" in verdicts[-1].reasons


def test_conversations_leave_social_motifs_to_collect(tmp_path):
    sim = game_sim(tmp_path, start="2023-02-13T12:00:00", end="2023-02-13T14:00:00", extra=("game.auto_requests=false",))
    sim.run(max_steps=200)
    sparks = events_of(sim, "sparkle")
    if not sparks:
        pytest.skip("no conversation happened in this window with the mock")  # pragma: no cover
    sp = sparks[0]
    assert CONTENT.motifs_for(sp["theme"], "social")[0].id == sp["motif"]
    visible = sim.game.visible_sparkles(sim.clock.now)
    if visible:
        sim.game.actions.append(sim.clock.step, "collect_sparkle", {"sparkle": visible[0]["id"]})
        sim.run(max_steps=1)
        assert any(e["source"] == "conversation" for e in events_of(sim, "motif"))


def test_the_papers_interventions_are_available_and_logged(tmp_path):
    sim = game_sim(tmp_path, extra=("game.auto_requests=false",))
    sim.initialize()
    stove = "the Ville:Isabella Rodriguez's apartment:main room:refrigerator"
    assert sim.world.exists(stove)
    sim.game.actions.append(0, "object_state", {"address": stove, "state": "empty"})
    sim.game.actions.append(0, "whisper", {"agent": "maria_lopez", "text": "You want to bake a cake for the party."})
    sim.run(max_steps=1)
    assert sim.world_state.get(stove).lasting == "empty" and sim.world_state.get(stove).lasting_source == "intervention"
    assert any(m.origin == MemoryOrigin.INNER_VOICE for m in sim.svc.store.for_agent("maria_lopez"))
    logged = [r for r in sim.db.query("SELECT json FROM events WHERE type='intervention'")]
    assert len(logged) == 2


def test_game_meters_never_reach_a_prompt(tmp_path):
    sim = game_sim(tmp_path)
    sim.initialize()
    sim.game.actions.append(0, "chat", {"agent": "klaus_mueller", "text": "How is your paper going?"})
    sim.game.actions.append(0, "gift", {"agent": "klaus_mueller", "gift": "pocket_notebook"})
    sim.run(max_steps=20)
    prompts = " ".join(r["system"] + r["prompt"] for r in sim.rt.ledger.rows())
    # Strings only the game's bookkeeping produces (identity text itself says "loves" and "cozy").
    for secret in ("friendship", "Town Pulse", "Sleepy Hamlet", "motif", "Ink Blot", "Melody Note", "affinity", "hearts"):
        assert secret not in prompts, secret
    assert "the town builder" in prompts.lower()  # the builder itself is in-world


# ---------------------------------------------------------------------- determinism
def _content(sim):
    tables = ("memories", "plans", "conversations", "agent_state", "spatial_memory", "world_objects", "game_items", "game_requests", "game_kv", "game_events")
    return sim.db.content_hash(tables)


def test_a_played_run_replays_exactly_without_any_model_call(tmp_path):
    a = game_sim(tmp_path, name="a")
    a.initialize()
    log = a.game.actions
    log.append(0, "chat", {"agent": "klaus_mueller", "text": "Hello! Do you like the library?"})
    log.append(2, "search", {"address": "the Ville:Hobbs Cafe:cafe:cafe customer seating"})
    log.append(5, "ask_request", {"agent": "isabella_rodriguez"})
    tiles = [t for t in a.world.walkable_tiles_for("the Ville:Johnson Park:park") if not a.world.names_at(*t)[2]]
    log.append(7, "build", {"ops": [{"op": "place", "catalog_id": "flower_planter", "x": tiles[5][0], "y": tiles[5][1], "paint": "sage"}]})
    assert a.run(max_steps=40) == "interrupted"
    r = Simulation(a.cfg, tmp_path / "replay", replay_from=tmp_path / "a")
    assert r.run(max_steps=40) == "interrupted", r.db.get_meta("stop_detail")
    assert r.rt.budget.usage.calls == 0 and _content(r) == _content(a)
    assert [p.address for p in r.game.store.items()] == [p.address for p in a.game.store.items()]


def test_resume_after_a_crash_reapplies_player_actions_once(tmp_path):
    full = game_sim(tmp_path, name="full")
    full.initialize()
    for sim in (full,):
        sim.game.actions.append(3, "chat", {"agent": "klaus_mueller", "text": "Good morning!"})
        sim.game.actions.append(40, "search", {"address": "the Ville:Oak Hill College:library:bookshelf"})
    full.run(max_steps=60)
    crash = game_sim(tmp_path, name="crash")
    crash.initialize()
    crash.game.actions.append(3, "chat", {"agent": "klaus_mueller", "text": "Good morning!"})
    crash.game.actions.append(40, "search", {"address": "the Ville:Oak Hill College:library:bookshelf"})
    crash.run(max_steps=45)  # checkpoint at 30; steps 31-45 are not committed
    crash.db.rollback()
    crash.db.close()
    resumed = Simulation(crash.cfg, tmp_path / "crash", provider=MockLLM(seed=5), embedding_provider=MockHashEmbedding(128))
    resumed.run(max_steps=60 - resumed.clock.step)
    assert _content(resumed) == _content(full)
    assert len([e for e in resumed.game.store.events() if e["kind"] == "motif"]) == 1
