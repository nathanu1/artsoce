"""Scenario import, seed policies and seeding (spec A-1 … A-7, D-8)."""

from __future__ import annotations

import json

import pytest

from generative_agents.config import repo_path
from generative_agents.scenario.loader import load_scenario
from helpers import make_sim

N25 = repo_path("scenarios/smallville_n25/scenario.yaml")


def test_n25_scenario_loads_all_agents_with_their_own_data():
    sc = load_scenario(N25)
    assert len(sc.agent_ids) == 25 and len(set(sc.agent_ids)) == 25
    assert sc.start.isoformat() == "2023-02-13T00:00:00" and sc.seconds_per_step == 10
    for aid in sc.agent_ids:
        spec = sc.agents[aid]
        assert spec.identity.id == aid and spec.seeds and spec.spatial_memory
        assert spec.perception == {"vision_r": 8, "att_bandwidth": 8, "retention": 8}
        texts = [s.text for s in spec.seeds]
        assert len(texts) == len(set(texts))  # no duplicated statements
    assert sc.world.describe()["sectors"] == 19


def test_party_knowledge_is_seeded_only_to_isabella():
    sc = load_scenario(N25)
    holders = {aid for aid in sc.agent_ids for s in sc.agents[aid].seeds if "party_knowledge" in s.flags}
    holders |= {aid for aid in sc.agent_ids if "party_knowledge" in sc.agents[aid].identity_flags}
    assert holders == {"isabella_rodriguez"}


def test_candidacy_policy_paper_vs_released_data():
    paper = load_scenario(N25)
    holders = {aid for aid in paper.agent_ids for s in paper.agents[aid].seeds if "candidacy_knowledge" in s.flags}
    assert holders == {"sam_moore"}
    dropped = [e for e in paper.seed_policy_log if e["action"] == "dropped"]
    assert [(e["agent"], e["seed_index"]) for e in dropped] == [("jennifer_moore", 10)]
    released = load_scenario(N25, candidacy_seed_policy="released_csv")
    holders = {aid for aid in released.agent_ids for s in released.agents[aid].seeds if "candidacy_knowledge" in s.flags}
    assert holders == {"sam_moore", "jennifer_moore"} and released.seed_policy_log == []
    assert len(released.agents["jennifer_moore"].seeds) == len(paper.agents["jennifer_moore"].seeds) + 1


def test_population_subset_and_unknown_agents():
    sc = load_scenario(N25, population=["sam_moore", "isabella_rodriguez"])
    assert sc.agent_ids == ["isabella_rodriguez", "sam_moore"]  # scenario order is kept
    with pytest.raises(ValueError):
        load_scenario(N25, population=["nobody"])


def test_events_stay_out_of_agent_data():
    sc = load_scenario(N25)
    assert sc.events["valentines_party"]["originator"] == "isabella_rodriguez"
    blob = json.dumps({aid: sc.agents[aid].identity.model_dump() for aid in sc.agent_ids})
    assert "probe_question" not in blob and "17:00" not in blob


def test_seeds_are_entered_once_verbatim_and_do_not_feed_the_trigger(tmp_path):
    sim = make_sim(tmp_path, ["isabella_rodriguez"])
    sim.initialize()
    spec = sim.scenario.agents["isabella_rodriguez"]
    rows = sim.db.query("SELECT description, origin, kind, seed FROM memories WHERE owner_id='isabella_rodriguez' ORDER BY seq")
    assert [r["description"] for r in rows] == [s.text.strip() for s in spec.seeds]
    assert {(r["origin"], r["kind"], r["seed"]) for r in rows} == {("seed", "observation", 1)}
    assert sim.svc.states.get("isabella_rodriguez").reflection_accumulator == 0
    from generative_agents.memory.seeds import seed_agent

    with pytest.raises(RuntimeError):
        seed_agent(sim.svc, spec, sim.clock.now)


def test_inner_thought_seed_rendering_keeps_the_original(tmp_path):
    sim = make_sim(tmp_path, ["isabella_rodriguez"], extra=("scenario.seed_rendering=inner_thought_llm",))
    sim.initialize()
    row = sim.db.one("SELECT description, metadata_json FROM memories WHERE owner_id='isabella_rodriguez' ORDER BY seq LIMIT 1")
    meta = json.loads(row["metadata_json"])
    assert meta["rendering"] == "inner_thought_llm" and meta["original"].startswith("You are excited")
    assert sim.rt.ledger.rows(task="seed_thought")
