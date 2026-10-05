"""Simulation mechanics: snapshot steps, checkpoint/resume, replay, budgets, isolation (spec K-*, L-*, O-*)."""

from __future__ import annotations

import json
import math

from generative_agents.providers.embeddings import MockHashEmbedding
from generative_agents.providers.mock import MockLLM
from generative_agents.simulation.engine import Simulation
from helpers import CountingLLM, make_sim, place, sim_config

TABLES = ("memories", "plans", "conversations", "agent_state", "spatial_memory", "world_objects", "embeddings")
PAIR = ["isabella_rodriguez", "klaus_mueller"]


def content(sim) -> str:
    return sim.db.content_hash(TABLES)


def test_resume_after_crash_matches_an_uninterrupted_run_without_paying_twice(tmp_path):
    a = make_sim(tmp_path, PAIR, provider=CountingLLM(MockLLM(seed=5)), name="a")
    assert a.run(max_steps=90) == "interrupted"
    assert a.clock.step == 90

    b_llm = CountingLLM(MockLLM(seed=5))
    b = make_sim(tmp_path, PAIR, provider=b_llm, name="b")
    b.run(max_steps=30)  # checkpoint at step 30
    for _ in range(25):  # steps 30..54 run but are never committed
        b.step()
    b.db.conn.close()  # crash: the open transaction is lost, the provider ledger is not

    b2_llm = CountingLLM(MockLLM(seed=5))
    b2 = Simulation(sim_config(PAIR), tmp_path / "b", provider=b2_llm, embedding_provider=MockHashEmbedding(128))
    assert b2.clock.step == 30
    b2.run(max_steps=60)
    assert b2.clock.step == 90
    assert content(b2) == content(a)
    assert len(b_llm.calls) + len(b2_llm.calls) == len(a.rt.provider.calls)  # crashed steps re-used from the ledger
    assert len(b2_llm.calls) < len(a.rt.provider.calls)


def test_replay_reproduces_the_run_without_any_model_call(tmp_path):
    a = make_sim(tmp_path, PAIR, name="a")
    a.run(max_steps=60)
    r = Simulation(sim_config(PAIR), tmp_path / "replay", replay_from=tmp_path / "a")
    status = r.run(max_steps=60)
    assert status != "failed", r.db.get_meta("stop_detail")
    assert content(r) == content(a)
    assert r.rt.budget.usage.calls == 0 and r.rt.budget.usage.cache_hits > 0
    manifest = json.loads((tmp_path / "replay" / "manifest.json").read_text())
    assert manifest["replay_of"]["run_id"] == "a"


def test_replay_that_diverges_stops_instead_of_calling_a_model(tmp_path):
    a = make_sim(tmp_path, PAIR, name="a")
    a.run(max_steps=10)
    cfg = sim_config(PAIR, extra=("planning.day_chunks_max=7",))  # a different setting changes the day-plan prompt
    r = Simulation(cfg, tmp_path / "replay", replay_from=tmp_path / "a")
    assert r.run(max_steps=10) == "failed"
    assert "diverged" in r.db.get_meta("stop_detail")["detail"]


def test_budget_exhaustion_rolls_back_and_resume_finishes(tmp_path):
    a = make_sim(tmp_path, PAIR, name="a")
    a.run(max_steps=60)
    c = make_sim(tmp_path, PAIR, name="c", extra=("budget.max_calls=20",))
    assert c.run(max_steps=60) == "budget_exhausted"
    stopped_at = c.clock.step
    assert stopped_at < 60 and stopped_at % 30 == 0  # back at the last checkpoint (0 = right after seeding)
    detail = c.db.get_meta("stop_detail")
    assert detail["status"] == "budget_exhausted" and "calls" in detail["detail"]
    assert c.db.get_meta("budget")["calls"] == c.rt.ledger.totals()["calls"]  # usage = real spend
    c.db.close()
    c2 = Simulation(sim_config(PAIR, extra=("budget.max_calls=100000",)), tmp_path / "c", embedding_provider=MockHashEmbedding(128), provider=MockLLM(seed=5))
    c2.run(max_steps=60 - stopped_at)
    assert content(c2) == content(a)


def test_perception_uses_the_start_of_step_snapshot(tmp_path):
    sim = make_sim(tmp_path, ["isabella_rodriguez", "sam_moore"])
    sim.initialize()
    place(sim, "isabella_rodriguez", (78, 19))
    place(sim, "sam_moore", (74, 21))
    sim.svc.states.flush()
    start = {aid: tuple(sim.svc.states.get(aid).tile) for aid in sim.order}
    sim.step()
    row = sim.db.one("SELECT metadata_json FROM memories WHERE owner_id='sam_moore' AND subject='Isabella Rodriguez' ORDER BY seq LIMIT 1")
    assert row is not None
    assert json.loads(row["metadata_json"])["distance"] == round(math.dist(start["sam_moore"], start["isabella_rodriguez"]), 2)


def test_frames_reconstruct_positions(tmp_path):
    sim = make_sim(tmp_path, PAIR)
    sim.run(max_steps=45)
    frames = [(r["step"], json.loads(r["json"])) for r in sim.db.query("SELECT step, json FROM frames ORDER BY step")]
    assert frames[0][0] == -1 and frames[0][1]["key"]
    state: dict[str, list] = {}
    for _step, f in frames:
        if f["key"]:
            state = dict(f["agents"])
        else:
            state.update(f["agents"])
    for aid in sim.order:
        tile = sim.svc.states.get(aid).tile
        assert state[aid][:2] == [tile[0], tile[1]]


def test_evaluator_ground_truth_never_reaches_a_prompt(tmp_path):
    sim = make_sim(tmp_path, ["isabella_rodriguez", "klaus_mueller", "sam_moore"])
    sim.run(max_steps=40)
    prompts = sim.rt.ledger.rows()
    assert prompts
    forbidden = [
        "Did you know there is a Valentine's Day party?",
        "Do you know who is running for mayor?",
        "EVALUATOR",
        "probe_question",
        "acceptance_patterns",
    ]
    for row in prompts:
        text = row["system"] + row["prompt"]
        assert not any(f in text for f in forbidden)
    # before any conversation, party knowledge appears only in its originator's prompts
    first_conv = sim.db.one("SELECT MIN(started_at) AS t FROM conversations")["t"]
    for row in prompts:
        if (first_conv is None or row["sim_time"] < first_conv) and "Valentine" in row["prompt"]:
            assert row["agent_id"] == "isabella_rodriguez"


def test_manifest_labels_mock_runs(tmp_path):
    sim = make_sim(tmp_path, PAIR)
    sim.run(max_steps=5)
    m = json.loads((tmp_path / "run" / "manifest.json").read_text())
    assert m["mode"] == "mock" and m["mock_llm"] and m["mock_embeddings"] and not m["research_grade"]
    assert m["prompts"] and m["scenario"]["agents"] == PAIR
    assert m["ledger"]["calls"] > 0


def test_no_model_calls_while_nothing_changes(tmp_path):
    from helpers import CountingLLM

    llm = CountingLLM(MockLLM(seed=5))
    sim = make_sim(tmp_path, ["klaus_mueller"], provider=llm, start="2023-02-13T01:00:00", end="2023-02-13T03:00:00")
    sim.run(max_steps=30)  # day plan, first perceptions, settling into sleep
    before = len(llm.calls)
    sim.run(max_steps=300)  # fifty minutes of uneventful sleep
    assert len(llm.calls) == before
