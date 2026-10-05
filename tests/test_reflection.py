"""Recursive reflection (spec E-1 … E-9) and evidence validation (E-6, E-7)."""

from __future__ import annotations

from datetime import timedelta

from generative_agents.cognition.reflection import ReflectionEngine
from generative_agents.memory.evidence import evidence_tree, has_cycle, validate_evidence
from generative_agents.providers.mock import MockLLM, ScriptedLLM
from generative_agents.schemas import MemoryKind, MemoryOrigin
from helpers import ISABELLA, KLAUS, T, make_stack

OBS = (MemoryKind.OBSERVATION, MemoryOrigin.DIRECT_OBSERVATION)


def observe(svc, ident, texts, importance=5, start=T):
    out = []
    for i, text in enumerate(texts):
        out.append(svc.remember(ident, text, *OBS, start + timedelta(minutes=i), importance=importance))
    return out


def test_trigger_requires_strictly_more_than_threshold():
    _, _, _, svc = make_stack()
    eng = ReflectionEngine(svc)
    observe(svc, KLAUS, [f"Klaus Mueller is reading article {i}" for i in range(30)], importance=5)  # sum 150
    assert svc.states.get(KLAUS.id).reflection_accumulator == 150
    assert not eng.should_reflect(KLAUS, T + timedelta(hours=1))  # paper: exceeds 150
    observe(svc, KLAUS, ["Klaus Mueller is taking notes"], importance=1, start=T + timedelta(hours=1))
    assert eng.should_reflect(KLAUS, T + timedelta(hours=2))


def test_reflections_and_plans_do_not_feed_the_trigger():
    _, _, _, svc = make_stack()
    svc.remember(KLAUS, "Klaus is dedicated to research", MemoryKind.REFLECTION, MemoryOrigin.INFERENCE, T, importance=9)
    svc.remember(KLAUS, "This is Klaus Mueller's plan for Monday", MemoryKind.PLAN, MemoryOrigin.INTENTION, T, importance=9)
    assert svc.states.get(KLAUS.id).reflection_accumulator == 0


def test_reflection_stores_evidence_linked_insights_and_resets():
    _, _, rt, svc = make_stack(overrides=["reflection.threshold=10"])  # TEST FIXTURE threshold
    eng = ReflectionEngine(svc)
    obs = observe(
        svc,
        KLAUS,
        [
            "Klaus Mueller is reading about gentrification",
            "Klaus Mueller is reading about urban design",
            "Klaus Mueller is making connections between the articles",
            "library table is being used to discuss research material",
        ],
        importance=4,
    )
    now = T + timedelta(hours=1)
    assert eng.should_reflect(KLAUS, now)
    report = eng.run(KLAUS, now)
    assert report["stored"] >= 1 and len(report["questions"]) == 3
    state = svc.states.get(KLAUS.id)
    assert state.reflection_accumulator == 0 and state.last_reflection_at == now and state.reflections_done == 1
    reflections = svc.store.for_agent(KLAUS.id, kinds=[MemoryKind.REFLECTION])
    obs_ids = {m.id for m in obs}
    for r in reflections:
        assert r.evidence_ids and set(r.evidence_ids) <= obs_ids and r.depth == 1
        assert not has_cycle(svc.store, r.id)
    events = svc.events.query("reflection")
    assert events and events[0]["batch_id"].endswith(".r0001")


def test_later_reflections_can_cite_earlier_ones_forming_a_tree():
    script = {
        "reflection_questions": [{"questions": ["What is Klaus passionate about?", "Who does Klaus see?", "What is Klaus doing?"]}],
        "reflection_insights": [
            {"insights": [{"insight": "Klaus Mueller spends many hours reading", "evidence": ["1", "2"]}]},
            {"insights": []},
            {"insights": [{"insight": "x", "evidence": ["1"]}]},
            {"insights": []},
            {"insights": [{"insight": "y", "evidence": ["1"]}]},
        ],
    }
    _, _, _, svc = make_stack(provider=ScriptedLLM(script, fallback=MockLLM(seed=1)), overrides=["reflection.threshold=5"])
    eng = ReflectionEngine(svc)
    observe(svc, KLAUS, ["Klaus Mueller is reading about gentrification", "Klaus Mueller is reading about urban design"], importance=4)
    eng.run(KLAUS, T + timedelta(hours=1))
    first = [m for m in svc.store.for_agent(KLAUS.id, kinds=[MemoryKind.REFLECTION]) if "many hours" in m.description][0]
    assert first.depth == 1
    # A later reflection citing the earlier one gets depth 2.
    second = svc.remember(
        KLAUS,
        "Klaus Mueller is highly dedicated to research",
        MemoryKind.REFLECTION,
        MemoryOrigin.INFERENCE,
        T + timedelta(hours=3),
        importance=7,
        evidence_ids=[first.id],
        depth=1 + first.depth,
    )
    tree = evidence_tree(svc.store, second.id)
    assert tree["evidence"][0]["id"] == first.id and tree["evidence"][0]["evidence"]


def test_malformed_insights_are_repaired_or_recorded_without_fabrication():
    script = {
        "reflection_questions": [{"questions": ["q1", "q2", "q3"]}],
        "reflection_insights": [
            {"insights": [{"insight": "cites a number that was never shown", "evidence": ["99"]}]},
            {"insights": [{"insight": "still bad", "evidence": []}]},
        ]
        * 3,
    }
    _, _, rt, svc = make_stack(provider=ScriptedLLM(script), overrides=["reflection.threshold=5"])
    eng = ReflectionEngine(svc)
    observe(svc, KLAUS, ["Klaus Mueller is reading", "Klaus Mueller is writing"], importance=4)
    before = svc.states.get(KLAUS.id).reflection_accumulator
    report = eng.run(KLAUS, T + timedelta(hours=1))
    assert report["stored"] == 0 and report["failures"]
    assert svc.store.for_agent(KLAUS.id, kinds=[MemoryKind.REFLECTION]) == []
    state = svc.states.get(KLAUS.id)
    assert state.reflection_accumulator == before  # kept, not reset
    assert state.reflection_retry_after == T + timedelta(hours=1, minutes=30)
    assert not eng.should_reflect(KLAUS, T + timedelta(hours=1, minutes=10))  # cooldown respected
    statuses = {r["status"] for r in rt.ledger.rows(task="reflection_insights")}
    assert statuses == {"invalid"}


def test_validate_evidence_rejects_foreign_unsupplied_and_missing():
    _, _, _, svc = make_stack()
    mine = observe(svc, KLAUS, ["Klaus Mueller is reading"])[0]
    theirs = observe(svc, ISABELLA, ["Isabella Rodriguez is baking"])[0]
    errs = validate_evidence(svc.store, KLAUS.id, [mine.id, theirs.id, "nope"], supplied_ids={theirs.id})
    joined = " ".join(errs)
    assert "not supplied" in joined and "another agent" in joined and "does not exist" in joined
    assert validate_evidence(svc.store, KLAUS.id, [], set())


def test_cycle_detection():
    _, db, _, svc = make_stack()
    a = observe(svc, KLAUS, ["a"])[0]
    b = svc.remember(KLAUS, "b", MemoryKind.REFLECTION, MemoryOrigin.INFERENCE, T, importance=3, evidence_ids=[a.id], depth=1)
    assert not has_cycle(svc.store, b.id)
    db.execute("UPDATE memories SET evidence_json=? WHERE id=?", (f'["{b.id}"]', a.id))  # corrupt on purpose
    assert has_cycle(svc.store, b.id)


def test_compat_trigger_counts_down_and_uses_access_ordered_window():
    _, _, _, svc = make_stack(overrides=["reflection.mode=released_code", "reflection.compat_trigger_max=20"])
    eng = ReflectionEngine(svc)
    eng.init_state(KLAUS.id)
    observe(svc, KLAUS, ["Klaus reads", "desk is idle", "Klaus writes"], importance=5)
    state = svc.states.get(KLAUS.id)
    assert state.reflection_countdown == 5 and not eng.should_reflect(KLAUS, T + timedelta(hours=1))
    observe(svc, KLAUS, ["Klaus talks to Maria"], importance=5, start=T + timedelta(minutes=10))
    assert state.reflection_countdown == 0 and eng.should_reflect(KLAUS, T + timedelta(hours=1))  # fires at <= 0
    window = eng.recent_records(KLAUS, T + timedelta(hours=1))
    assert all("idle" not in m.description for m in window) and len(window) == 3


def test_no_quota_is_enforced():
    _, _, _, svc = make_stack()
    eng = ReflectionEngine(svc)
    observe(svc, KLAUS, ["Klaus reads"], importance=2)
    assert not eng.should_reflect(KLAUS, T + timedelta(days=1))  # nothing forces a daily reflection


def test_reflection_disabled_architecture_never_reflects():
    _, _, _, svc = make_stack(overrides=["architecture.reflection=false", "reflection.threshold=1"])
    eng = ReflectionEngine(svc)
    observe(svc, KLAUS, ["Klaus reads", "Klaus writes"], importance=9)
    assert not eng.should_reflect(KLAUS, T + timedelta(hours=1))
