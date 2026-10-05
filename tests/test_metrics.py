"""Known toy examples for diffusion, mutual-knowledge density, attendance and failures (spec N-1 … N-4)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from eval_helpers import frames, snapshot, toy_run
from generative_agents.config import repo_path
from generative_agents.evaluation import attendance as att
from generative_agents.evaluation import diffusion as dif
from generative_agents.evaluation import relationships as rel
from generative_agents.evaluation.evidence import Topic, load_topics
from generative_agents.evaluation.failures import taxonomy
from generative_agents.evaluation.interview import InterviewSession
from generative_agents.memory.masks import FULL
from generative_agents.providers.embeddings import MockHashEmbedding
from generative_agents.providers.mock import MockLLM, ScriptedLLM
from generative_agents.scenario.loader import load_scenario
from generative_agents.world.hierarchy import WorldMap

EVENTS = load_scenario(repo_path("scenarios/smallville_n25/scenario.yaml")).events
PARTY = load_topics(EVENTS)["valentines_party"]


def yes(text="Yes, there is a Valentine's Day party at Hobbs Cafe on February 14th."):
    return {"answer": text}


def label(claims, details=()):
    return {"claims_knowledge": claims, "details": list(details), "quote": ""}


def test_transmissions_record_sender_receiver_and_details():
    _, db, _, _ = toy_run()
    t = dif.transmissions(db, PARTY)
    assert len(t) == 1
    assert (t[0]["sender"], t[0]["receiver"], t[0]["conversation_id"]) == ("isabella_rodriguez", "klaus_mueller", "c00001")
    assert set(t[0]["details"]) >= {"date", "place", "time"} and t[0]["invitation"]
    assert dif.first_exposures(t)["klaus_mueller"]["sender"] == "isabella_rodriguez"


def test_awareness_separates_supported_claims_from_hallucination_and_retrieval_failure(tmp_path):
    cfg, db, _, _ = toy_run()
    snap = snapshot(db, tmp_path / "s.sqlite")
    # Isabella: claims, supported by seed. Klaus: denies despite evidence. Maria: claims with no evidence.
    script = {
        "interview": [yes(), {"answer": "No, I haven't heard of any party."}, yes("Yes, I heard about it.")],
        "awareness": [label(True, ["date", "place"]), label(False), label(True, ["time"])],
    }
    s = InterviewSession(
        cfg, snap, ledger_path=None, scope="p", mask=FULL, provider=ScriptedLLM(script, fallback=MockLLM(seed=1)), embedding_provider=MockHashEmbedding(128)
    )
    rows = {r["agent_id"]: r for r in dif.probe_awareness(s, PARTY, ["isabella_rodriguez", "klaus_mueller", "maria_lopez"])}
    assert rows["isabella_rodriguez"]["status"] == "aware" and rows["isabella_rodriguez"]["originator"]
    assert rows["klaus_mueller"]["status"] == "retrieval_failure"
    assert rows["maria_lopez"]["status"] == "claimed_unsupported" and rows["maria_lopez"]["unsupported_details"] == ["time"]
    summ = dif.summarize(list(rows.values()))
    assert (summ["claimed"], summ["supported_aware"], summ["newly_informed_supported"], summ["claimed_unsupported"]) == (2, 1, 0, 1)


def test_density_convention_and_mutual_supported_edges():
    assert rel.density(0, 0) is None and rel.density(1, 0) is None
    assert rel.density(3, 1) == pytest.approx(1 / 3)
    rows = [
        {"asker": "a", "about": "b", "claims_knowledge": True, "status": "supported"},
        {"asker": "b", "about": "a", "claims_knowledge": True, "status": "supported"},
        {"asker": "a", "about": "c", "claims_knowledge": True, "status": "supported"},
        {"asker": "c", "about": "a", "claims_knowledge": True, "status": "hallucinated"},
        {"asker": "b", "about": "c", "claims_knowledge": False, "status": "denies"},
        {"asker": "c", "about": "b", "claims_knowledge": True, "status": "observed_only"},
    ]
    g = rel.graph(rows, ["a", "b", "c"])
    assert g["edges_supported"] == [["a", "b"]] and g["density_supported"] == pytest.approx(1 / 3)
    assert g["edges_claimed"] == [["a", "b"], ["a", "c"]]
    assert (g["hallucinated"], g["observed_only"], g["affirmative"]) == (1, 1, 5)


def test_relationship_probe_validates_answers_against_memory(tmp_path):
    cfg, db, _, _ = toy_run()
    snap = snapshot(db, tmp_path / "s.sqlite")
    s = InterviewSession(cfg, snap, ledger_path=None, scope="r", mask=FULL, provider=MockLLM(seed=1), embedding_provider=MockHashEmbedding(128))
    rows = rel.probe_relationships(s, ["klaus_mueller", "maria_lopez"])
    by = {(r["asker"], r["about"]): r for r in rows}
    assert "seed" in by[("klaus_mueller", "maria_lopez")]["evidence_kinds"]
    assert "seed" in by[("maria_lopez", "klaus_mueller")]["evidence_kinds"]


@pytest.fixture(scope="module")
def world():
    return WorldMap.load(repo_path("scenarios/smallville_n25/map/the_ville.json"))


def test_attendance_is_physical_and_uses_separate_denominators(world):
    _, db, _, _ = toy_run()
    start, end = PARTY.window
    cafe = world.walkable_tiles_for("the Ville:Hobbs Cafe")[0]
    away = world.walkable_tiles_for("the Ville:Johnson Park")[0]
    step0 = start - timedelta(minutes=30)
    frames(
        db,
        [
            (0, step0, True, {"isabella_rodriguez": cafe, "klaus_mueller": away, "maria_lopez": away}),
            (1, start + timedelta(minutes=5), False, {"klaus_mueller": cafe}),  # Klaus arrives and stays 115 minutes
            (2, start + timedelta(minutes=30), False, {"maria_lopez": cafe}),  # Maria drops in for 4 minutes
            (3, start + timedelta(minutes=34), False, {"maria_lopez": away}),
            (4, end + timedelta(minutes=10), True, {"isabella_rodriguez": away, "klaus_mueller": away, "maria_lopez": away}),
        ],
    )
    rep = att.attendance(
        db, world, PARTY, ["isabella_rodriguez", "klaus_mueller", "maria_lopez"], host="isabella_rodriguez", seconds_per_step=10, min_minutes=10
    )
    rows = {r["agent_id"]: r for r in rep["rows"]}
    assert rows["klaus_mueller"]["attended"] and rows["klaus_mueller"]["present_minutes"] == pytest.approx(115)
    assert not rows["maria_lopez"]["attended"] and rows["maria_lopez"]["present_minutes"] == pytest.approx(4)
    assert rows["klaus_mueller"]["invited"] and rows["klaus_mueller"]["accepted"] and rows["klaus_mueller"]["exposed"]
    assert not rows["maria_lopez"]["invited"] and not rows["maria_lopez"]["exposed"]
    s = rep["summary"]
    assert s["among_invited"] == {"attended": 1, "n": 1, "rate": 1.0}  # host excluded
    assert s["host_present"] and s["present_guests"] == 1 and s["denominators_exclude_host"]
    assert s["among_scheduled"]["n"] == 0  # accepting is not scheduling


def test_failure_taxonomy_categories_and_examples(world):
    _, db, _, _ = toy_run()
    diffusion_rows = [
        {"event": "valentines_party", "agent_id": "maria_lopez", "status": "unaware", "answer": "No.", "evidence": [], "unsupported_details": []},
        {
            "event": "valentines_party",
            "agent_id": "klaus_mueller",
            "status": "retrieval_failure",
            "answer": "No idea.",
            "evidence": [{"memory_id": "m1"}],
            "unsupported_details": [],
        },
        {"event": "valentines_party", "agent_id": "x", "status": "claimed_unsupported", "answer": "Yes!", "evidence": [], "unsupported_details": ["time"]},
    ]
    out = taxonomy(db, diffusion_rows=diffusion_rows, relationship_rows=[{"asker": "a", "about": "b", "status": "hallucinated", "answer": "Sure"}])
    assert out["missed_exposure"]["count"] == 1 and out["retrieval_failure"]["count"] == 1
    assert out["ungrounded_inference"]["count"] == 2 and out["unsupported_embellishment"]["count"] == 1
    assert out["overly_agreeable_or_formal"]["count"] == 1  # "That sounds great, I'd love to come!"
    assert all(v["rule"] for v in out.values())


def test_topic_matching_respects_require_all():
    cand = Topic.from_event("mayor_candidacy", EVENTS["mayor_candidacy"])
    assert cand.matches("Sam Moore is running for mayor") and not cand.matches("The mayor gave a speech")
    assert PARTY.details_in("party at Hobbs Cafe at 5pm on February 14") == ["date", "place", "time"]
