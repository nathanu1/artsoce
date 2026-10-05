"""Cached dynamic summary (Appendix A; spec F-1 … F-3) and mask isolation (M-2)."""

from __future__ import annotations

from datetime import timedelta

from generative_agents.cognition.summary import SummaryService
from generative_agents.memory.masks import FULL, NO_MEMORY, NO_REFLECTION
from generative_agents.schemas import MemoryKind, MemoryOrigin
from helpers import ISABELLA, T, make_stack


def seed(svc):
    svc.remember(ISABELLA, "Isabella Rodriguez is serving coffee at Hobbs Cafe", MemoryKind.OBSERVATION, MemoryOrigin.DIRECT_OBSERVATION, T, importance=3)
    svc.remember(
        ISABELLA, "Isabella Rodriguez values making people feel welcome", MemoryKind.REFLECTION, MemoryOrigin.INFERENCE, T, importance=7, evidence_ids=[]
    )


def test_summary_uses_three_appendix_a_queries_and_caches():
    _, _, rt, svc = make_stack()
    seed(svc)
    s = SummaryService(svc)
    text = s.dynamic(ISABELLA, T)
    assert text
    traces = svc.traces.for_agent(ISABELLA.id, limit=10)
    queries = {t["query"] for t in traces}
    assert queries == {
        "Isabella Rodriguez's core characteristics",
        "Isabella Rodriguez's current daily occupation",
        "Isabella Rodriguez's feeling about their recent progress in life",
    }
    calls = len(rt.ledger.rows(task="summary_aspect"))
    assert s.dynamic(ISABELLA, T + timedelta(minutes=30)) == text
    assert len(rt.ledger.rows(task="summary_aspect")) == calls  # served from cache


def test_refresh_policy_interval_and_new_day():
    _, _, rt, svc = make_stack(overrides=["summary.refresh_every_minutes=60"])
    seed(svc)
    s = SummaryService(svc)
    s.dynamic(ISABELLA, T)
    n0 = len(rt.ledger.rows(task="summary_aspect"))
    s.dynamic(ISABELLA, T + timedelta(minutes=61))
    n1 = len(rt.ledger.rows(task="summary_aspect"))
    assert n1 > n0
    s.dynamic(ISABELLA, T.replace(hour=23, minute=59) + timedelta(minutes=2))  # next day
    assert len(rt.ledger.rows(task="summary_aspect")) > n1


def test_masked_summaries_are_isolated_from_the_full_cache():
    _, _, _, svc = make_stack()
    seed(svc)
    s = SummaryService(svc)
    s.dynamic(ISABELLA, T, mask=FULL)
    s.dynamic(ISABELLA, T, mask=NO_REFLECTION)
    state = svc.states.get(ISABELLA.id)
    assert set(state.summaries) == {FULL.key, NO_REFLECTION.key}
    # The no-reflection summary was built without the reflection memory.
    nr_traces = [t for t in svc.traces.for_agent(ISABELLA.id, limit=20)]
    nr_delivered = set()
    for t in nr_traces:
        nr_delivered |= set(t["delivered"])
    refl_id = [m.id for m in svc.store.for_agent(ISABELLA.id, kinds=[MemoryKind.REFLECTION])][0]
    no_refl_traces = [t for t in nr_traces if all(c["kind"] != "reflection" for c in t["candidates"])]
    assert no_refl_traces, "masked retrievals must not even consider reflections"
    assert refl_id in nr_delivered  # (the full-architecture summary could use it)


def test_no_memory_condition_gets_identity_only_and_no_calls():
    _, _, rt, svc = make_stack()
    seed(svc)
    s = SummaryService(svc)
    assert s.dynamic(ISABELLA, T, mask=NO_MEMORY) == ""
    desc = s.description(ISABELLA, T, mask=NO_MEMORY)
    assert desc.startswith("Name: Isabella Rodriguez") and "Current Date: Monday February 13" in desc
    assert rt.ledger.rows(task="summary_aspect") == []
