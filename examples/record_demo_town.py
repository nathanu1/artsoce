"""Record the demo town: a mock run from 07:00 to 13:00 with a scripted player.

The player chats, gives a gift, searches an object, collects a sparkle, builds in the Town Square
and fulfils one resident's wish. Actions go through GameSession.submit exactly as the web UI's
would, so the run replays with zero model calls. This is how the published recording was made:

    python examples/record_demo_town.py runs/demo-town
    cd frontend && npm run build:demo && cd ..
    ga export-demo --run-dir runs/demo-town --out frontend/dist-demo
    python -m http.server -d frontend/dist-demo 8090    # then open http://127.0.0.1:8090/demo.html
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from generative_agents.config import load_config
from generative_agents.game.session import GameSession
from generative_agents.simulation.engine import save_config

RUN = Path(sys.argv[1] if len(sys.argv) > 1 else "runs/demo-town")
END_HOUR = 13

cfg = load_config(
    "configs/town_mock.yaml",
    overrides=[
        "scenario.start=2023-02-13T07:00:00",
        f"scenario.end=2023-02-13T{END_HOUR:02d}:00:00",
        "run.name=demo-town",
        "run.label=town game demo (MOCK)",
    ],
)
shutil.rmtree(RUN, ignore_errors=True)
RUN.mkdir(parents=True)
save_config(cfg, RUN)
session = GameSession(cfg, RUN, speed="max")
sim, game = session.sim, session.game


def at(hh: int, mm: int) -> int:
    return ((hh - 7) * 60 + mm) * 6  # 10-second steps from 07:00


def free(aid: str) -> bool:
    v = sim.view_of(aid)
    return not v.sleeping and not v.conversation_partner


def log(msg: str) -> None:
    print(f"{sim.clock.now:%H:%M}  {msg}", flush=True)


def find_spot(ops_for, tiles):
    for x, y in tiles:
        ops = ops_for(x, y)
        if game.validate_build(ops)["ok"]:
            return ops
    return None


# timed actions that need the resident to be free (retried each step until then)
queue: list[tuple[int, str, dict]] = [
    (at(8, 5), "chat", {"agent": "klaus_mueller", "text": "Good morning, Klaus! What are you working on today?"}),
    (at(8, 40), "chat", {"agent": "isabella_rodriguez", "text": "Morning, Isabella! How is the cafe today?"}),
    (at(9, 50), "gift", {"agent": "isabella_rodriguez", "gift": "spiced_cocoa"}),
    (at(12, 5), "whisper", {"agent": "klaus_mueller", "text": "You would like to show Maria the new bench in the Town Square."}),
    (at(12, 30), "chat", {"agent": "klaus_mueller", "text": "Have you seen the new bench in the Town Square?"}),
]
done = {"search": False, "square": False, "wish": None, "delivered": False, "sparkle": False, "maria_chat": False}

sim.begin()
session._ready = True
game.ensure_started(sim.clock.now)
session._publish(frame=True)

objects = {a for a in sim.world.address_tiles if a.count(":") == 3}
search_target = next((a for a in sorted(objects) if a.startswith("the Ville:Hobbs Cafe:cafe:") and "counter" in a), None) or next(
    a for a in sorted(objects) if a.startswith("the Ville:Hobbs Cafe:")
)

while not session.finished:
    step = sim.clock.step
    now = sim.clock.now
    for item in list(queue):
        due, kind, payload = item
        if step >= due and (kind == "whisper" or free(payload["agent"])):
            session.submit(kind, payload)
            queue.remove(item)
            log(f"{kind} {payload.get('agent')}")
    if not done["search"] and step >= at(9, 25):
        session.submit("search", {"address": search_target})
        done["search"] = True
        log(f"search {search_target}")
    if not done["square"] and step >= at(10, 30):
        square = [(x, y) for y in range(31, 36) for x in range(72, 86)]
        ops = find_spot(
            lambda x, y: [
                {"op": "place", "catalog_id": "flower_planter", "x": x, "y": y, "rot": 0, "paint": "sage"},
                {"op": "place", "catalog_id": "bench", "x": x + 2, "y": y, "rot": 0, "paint": None},
            ],
            square,
        )
        if ops:
            session.submit("build", {"ops": ops})
            done["square"] = True
            log(f"build in the Town Square at {ops[0]['x']},{ops[0]['y']}")
    if done["wish"] is None and step >= at(11, 0):
        level = game.level()
        for req in game.store.requests():
            if req["status"] != "open":
                continue
            items = [it for it in game.content.items if it.theme == req["theme"] and it.unlock <= level]
            tiles = sorted(sim.world.address_tiles.get(req["place_address"], []))
            ops = None
            for it in items:
                ops = find_spot(lambda x, y, it=it: [{"op": "place", "catalog_id": it.id, "x": x, "y": y, "rot": 0, "paint": None}], tiles)
                if ops:
                    break
            if ops:
                session.submit("build", {"ops": ops})
                done["wish"] = req["id"]
                log(f"build for {req['agent_id']}'s wish ({req['wish']}) at {req['place_label']}: {ops[0]['catalog_id']}")
                break
        else:
            done["wish"] = ""
            log("no wish could be fulfilled")
    if done["wish"] and not done["delivered"]:
        req = next((r for r in game.store.requests() if r["id"] == done["wish"]), None)
        if req and req["status"] == "ready" and free(req["agent_id"]):
            session.submit("deliver", {"request": req["id"]})
            done["delivered"] = True
            log(f"deliver to {req['agent_id']}")
    if not done["sparkle"] and step >= at(10, 0):
        vis = game.visible_sparkles(now)
        if vis:
            session.submit("collect_sparkle", {"sparkle": vis[0]["id"]})
            done["sparkle"] = True
            log(f"collect sparkle {vis[0]['id']} ({vis[0]['theme']})")
    if done["delivered"] and not done["maria_chat"] and step >= at(11, 50) and free("maria_lopez"):
        session.submit("chat", {"agent": "maria_lopez", "text": "Hi Maria! What are you up to this afternoon?"})
        done["maria_chat"] = True
        log("chat maria_lopez")
    sim.advance()
    session._publish(frame=True)

events = [e["kind"] for e in session._feed]
print("events:", {k: events.count(k) for k in sorted(set(events))})
print("pulse:", game.store.get("pulse"), "items:", len(game.store.items()), "requests:", [(r["agent_id"], r["status"]) for r in game.store.requests()])
sim.finish(sim.wind_down())
sim.close()
