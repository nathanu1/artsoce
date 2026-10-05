"""Reactions, constraints and dialogue inside the running simulation (spec H-*, I-*, J-5 … J-7).

Every scenario runs the real engine on the Smallville map with the offline mock model.
"""

from __future__ import annotations

import json
from datetime import datetime

from generative_agents.cognition.dialogue import DialogueEngine, Side, conversation_minutes
from generative_agents.cognition.reaction import ReactionEngine
from generative_agents.cognition.summary import SummaryService
from generative_agents.providers.mock import MockLLM, ScriptedLLM
from generative_agents.schemas import MemoryOrigin, PlanLevel, Utterance
from helpers import ISABELLA, KLAUS, make_sim, make_stack, place

DORM = "the Ville:Dorm for Oak Hill College"
STOVE = f"{DORM}:kitchen:cooking area"
FRIDGE = f"{DORM}:kitchen:refrigerator"
T9 = datetime(2023, 2, 13, 9, 0)


def ready(sim, placements):
    sim.initialize()
    for aid, tile in placements.items():
        place(sim, aid, tile)
    sim.svc.states.flush()
    sim.db.commit()


def memories(sim, aid, origin=None):
    sql = "SELECT description, origin, conversation_id FROM memories WHERE owner_id=?"
    rows = sim.db.query(sql, (aid,))
    return [r for r in rows if origin is None or r["origin"] == origin]


def test_burning_stove_is_noticed_and_put_out(tmp_path):
    sim = make_sim(tmp_path, ["klaus_mueller"])
    ready(sim, {"klaus_mueller": (118, 45)})
    sim.schedule_intervention({"at": T9.isoformat(), "kind": "object_state", "address": STOVE, "state": "burning"})
    sim.run(max_steps=20)
    assert any(r["description"] == "cooking area is burning" for r in memories(sim, "klaus_mueller"))
    reactions = sim.svc.events.query("reaction", agent_id="klaus_mueller")
    fire = [r for r in reactions if r["observation"] == "cooking area is burning"]
    assert fire and fire[0]["decision"] == "react"
    inserted = [p for p in sim.plans.items("klaus_mueller", level=PlanLevel.TASK) if p.source == "reaction"]
    assert inserted and "fire" in inserted[0].description
    assert sim.world_state.get(STOVE).lasting == "turned off"  # left in a lasting new condition
    assert sim.svc.events.query("object_state", agent_id="klaus_mueller")


def test_empty_fridge_prompts_a_shopping_trip(tmp_path):
    sim = make_sim(tmp_path, ["klaus_mueller"])
    ready(sim, {"klaus_mueller": (120, 45)})
    sim.schedule_intervention({"at": T9.isoformat(), "kind": "object_state", "address": FRIDGE, "state": "empty"})
    sim.run(max_steps=3)
    reactions = [r for r in sim.svc.events.query("reaction", agent_id="klaus_mueller") if r["observation"] == "refrigerator is empty"]
    assert reactions and reactions[0]["decision"] == "react" and "groceries" in reactions[0]["new_activity"]
    assert len(reactions) == 1  # considered once, not every step
    act = sim.svc.states.get("klaus_mueller").action
    assert "groceries" in act.description and act.address and "Willows Market" in act.address
    assert sim.world_state.get(FRIDGE).lasting == "empty"  # nothing refilled it


def test_sleeping_agents_store_what_they_perceive_but_do_not_react(tmp_path):
    sim = make_sim(tmp_path, ["maria_lopez"], start="2023-02-13T08:00:00")
    ready(sim, {"maria_lopez": (120, 45)})  # mock plan: Maria sleeps until 10:00
    sim.schedule_intervention({"at": "2023-02-13T08:00:00", "kind": "object_state", "address": FRIDGE, "state": "empty"})
    sim.run(max_steps=3)
    assert "refrigerator is empty" in [r["description"] for r in memories(sim, "maria_lopez")]
    assert sim.svc.events.query("reaction", agent_id="maria_lopez") == []


def test_occupied_single_person_bathroom_makes_the_agent_wait(tmp_path):
    sim = make_sim(tmp_path, ["klaus_mueller", "wolfgang_schulz"])
    ready(sim, {"klaus_mueller": (106, 50), "wolfgang_schulz": (117, 46)})
    now = sim.clock.now
    views = sim.views()
    occ = sim._occupancy(views)
    ident = sim.identities["wolfgang_schulz"]
    sim.planner.ensure_day(ident, now)
    task = sim.planner.insert(ident, now, "take a shower", 15, source="generated")
    sim._start_action(ident, task, now, occ, views)
    act = sim.svc.states.get("wolfgang_schulz").action
    assert act.kind == "wait" and "bathroom" in act.description
    fb = memories(sim, "wolfgang_schulz", MemoryOrigin.SYSTEM_FEEDBACK.value)
    assert fb and "occupied" in fb[0]["description"]
    assert sim.svc.events.query("constraint", agent_id="wolfgang_schulz")[0]["rule"] == "occupied"


def test_without_constraints_the_bathroom_is_entered(tmp_path):
    sim = make_sim(tmp_path, ["klaus_mueller", "wolfgang_schulz"], extra=("constraints.policy=none",))
    ready(sim, {"klaus_mueller": (106, 50), "wolfgang_schulz": (117, 46)})
    now = sim.clock.now
    views = sim.views()
    ident = sim.identities["wolfgang_schulz"]
    sim.planner.ensure_day(ident, now)
    task = sim.planner.insert(ident, now, "take a shower", 15, source="generated")
    sim._start_action(ident, task, now, sim._occupancy(views), views)
    act = sim.svc.states.get("wolfgang_schulz").action
    assert act.kind == "plan" and "man's bathroom" in act.address


def test_private_room_is_refused_and_the_agent_chooses_again(tmp_path):
    script = {
        "choose_location": [
            {"choice": "Dorm for Oak Hill College"},
            {"choice": "Klaus Mueller's room"},
            {"choice": "Dorm for Oak Hill College"},
            {"choice": "common room"},
        ]
    }
    sim = make_sim(tmp_path, ["klaus_mueller", "wolfgang_schulz"], provider=ScriptedLLM(script, fallback=MockLLM(seed=5)))
    ready(sim, {"wolfgang_schulz": (117, 46)})
    sim.spatial.get("wolfgang_schulz").learn("the Ville", "Dorm for Oak Hill College", "Klaus Mueller's room", "desk")
    now = sim.clock.now
    ident = sim.identities["wolfgang_schulz"]
    views = sim.views()
    loc = sim.locations.choose(
        ident,
        "visit a friend",
        now,
        ("Dorm for Oak Hill College", "common room"),
        sim.spatial.get("wolfgang_schulz"),
        check=lambda a: sim.constraints.check(ident, a, now, sim._occupancy(views)),
    )
    assert loc.rejections and loc.rejections[0]["rule"] == "private"
    assert loc.address and loc.address.startswith(f"{DORM}:common room")
    assert any("private room" in r["description"] for r in memories(sim, "wolfgang_schulz", MemoryOrigin.SYSTEM_FEEDBACK.value))


def test_street_fire_seen_by_a_passerby(tmp_path):
    sim = make_sim(tmp_path, ["sam_moore"])
    ready(sim, {"sam_moore": (76, 28)})
    sim.schedule_intervention(
        {
            "at": T9.isoformat(),
            "kind": "ambient",
            "id": "street_fire",
            "tile": [77, 28],
            "subject": "fire",
            "object": "burning",
            "description": "a fire is burning on the street",
        }
    )
    sim.run(max_steps=2)
    obs = [r["description"] for r in memories(sim, "sam_moore")]
    assert "a fire is burning on the street" in obs
    r = [e for e in sim.svc.events.query("reaction", agent_id="sam_moore") if "fire" in e["observation"]]
    assert r and r[0]["decision"] == "react"


TALK = {"decision": "talk", "reason": "They are friends.", "new_activity": None, "duration_minutes": None}


def test_nearby_friend_conversation_is_private_and_turn_by_turn(tmp_path):
    sim = make_sim(
        tmp_path, ["isabella_rodriguez", "maria_lopez", "klaus_mueller", "sam_moore"], provider=ScriptedLLM({"reaction": [TALK]}, fallback=MockLLM(seed=5))
    )
    ready(sim, {"isabella_rodriguez": (78, 19), "klaus_mueller": (80, 21), "sam_moore": (74, 21), "maria_lopez": (118, 45)})
    sim.run(max_steps=3)
    convs = [json.loads(r["json"]) for r in sim.db.query("SELECT json FROM conversations")]
    c = next(c for c in convs if set(c["participants"]) >= {"isabella_rodriguez"})
    assert c["status"] == "completed" and len(c["utterances"]) >= 2
    turns = [r for r in sim.rt.ledger.rows(task="dialogue_turn") if r["sim_time"] == c["started_at"]]
    assert len(turns) >= len(c["utterances"])  # one call per utterance (plus any repairs)
    a, b = c["participants"]
    for aid in (a, b):
        heard = [m for m in memories(sim, aid) if m["conversation_id"] == c["id"]]
        assert len(heard) == len(c["utterances"]) + 1  # every line + the summary
        assert sim.svc.states.get(aid).action.kind == "conversation"
    texts = [u["text"] for u in c["utterances"]]
    for outsider in {"isabella_rodriguez", "klaus_mueller", "sam_moore", "maria_lopez"} - {a, b}:
        mine = " ".join(m["description"] for m in memories(sim, outsider))
        assert not any(t in mine for t in texts)
        prompts = " ".join(r["prompt"] for r in sim.rt.ledger.rows(agent_id=outsider))
        assert not any(t in prompts for t in texts)
    # the partner never sees the initiator's private seed text in its own prompts
    seed = "You are excited to be planning a Valentine's Day party"
    partner = b if a == "isabella_rodriguez" else a
    assert not any(seed in r["prompt"] for r in sim.rt.ledger.rows(agent_id=partner))
    assert sim.svc.states.get(a).cooldown_until.get(b)


def _dialogue(provider, max_utterances=16):
    cfg, db, rt, svc = make_stack(provider, [f"dialogue.max_utterances={max_utterances}"])
    summary = SummaryService(svc)
    eng = DialogueEngine(svc, summary, ReactionEngine(svc, summary))
    return eng, svc


def _sides():
    return Side(ISABELLA, "Isabella Rodriguez is serving coffee", "Klaus Mueller is reading"), Side(
        KLAUS, "Klaus Mueller is reading", "Isabella Rodriguez is serving coffee"
    )


def test_dialogue_stops_at_the_utterance_cap():
    lines = [{"utterance": f"line {i}", "end_conversation": False} for i in range(30)]
    eng, svc = _dialogue(ScriptedLLM({"dialogue_turn": lines}, fallback=MockLLM(seed=2)), max_utterances=6)
    conv = eng.run(*_sides(), T9, "the Ville:Hobbs Cafe:cafe")
    assert len(conv.utterances) == 6 and "limit" in conv.reason
    assert [u.speaker_id for u in conv.utterances] == [ISABELLA.id, KLAUS.id] * 3


def test_dialogue_ends_when_a_speaker_ends_it():
    lines = [{"utterance": "Hi Klaus!", "end_conversation": False}, {"utterance": "Bye!", "end_conversation": True}]
    eng, _ = _dialogue(ScriptedLLM({"dialogue_turn": lines}, fallback=MockLLM(seed=2)))
    conv = eng.run(*_sides(), T9, None)
    assert [u.text for u in conv.utterances] == ["Hi Klaus!", "Bye!"] and conv.status == "completed"


def test_failed_turn_aborts_without_inventing_lines():
    lines = [{"utterance": "Hi Klaus!", "end_conversation": False}, "not json", "still not json"]
    eng, svc = _dialogue(ScriptedLLM({"dialogue_turn": lines}, fallback=MockLLM(seed=2)))
    conv = eng.run(*_sides(), T9, None)
    assert conv.status == "failed" and [u.text for u in conv.utterances] == ["Hi Klaus!"]
    stored = [m for m in svc.store.for_agent(KLAUS.id) if m.conversation_id == conv.id]
    assert [m.origin for m in stored if m.origin != MemoryOrigin.CONVERSATION] == [MemoryOrigin.STATEMENT]


def test_conversation_duration_rule():
    u = [Utterance(speaker_id="a", text="x" * 240, sim_time=T9), Utterance(speaker_id="b", text="y" * 241, sim_time=T9)]
    assert conversation_minutes(u) == 2  # ceil(int(481 / 8) / 30) = ceil(60 / 30)
    assert conversation_minutes(u[:1]) == 1
