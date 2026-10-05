"""Paper-mode retrieval (spec C-1 … C-8, C-11) and released-code compatibility (C-9, C-10)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from conftest import T0, Env, FixedEmbedder, hours
from generative_agents.db import Database
from generative_agents.memory.retrieval import (
    RetrievalSettings,
    Retriever,
    Weights,
    cosine_to,
    keyword_lookup,
    normalize_minmax,
)
from generative_agents.memory.trace import TraceStore
from generative_agents.schemas import MemoryKind, MemoryOrigin


def paper(**kw):
    base = dict(budget_tokens=None, max_items=None)
    base.update(kw)
    return RetrievalSettings(**base)


def test_recency_is_elapsed_time_decay(env):
    m = env.add("a", "cleaning the kitchen", created=T0)
    r = Retriever(env.store, env.embedder, paper())
    now = T0 + hours(10)
    [c] = r.score([m], "kitchen", now)
    assert c.raw_recency == pytest.approx(0.995**10)


def test_recency_uses_fractional_hours_and_clamps_negative(env):
    m = env.add("a", "reading a book", created=T0, accessed=T0 + hours(2))
    r = Retriever(env.store, env.embedder, paper())
    [c] = r.score([m], "book", T0 + hours(2.5))
    assert c.raw_recency == pytest.approx(0.995**0.5)
    [c2] = r.score([m], "book", T0)  # access after "now": gap clamps to zero
    assert c2.raw_recency == pytest.approx(1.0)


def test_normalization_bounds_and_constant_component():
    v = np.array([3.0, 7.0, 5.0])
    n = normalize_minmax(v)
    assert n.min() == 0.0 and n.max() == 1.0 and n[2] == pytest.approx(0.5)
    assert list(normalize_minmax(np.array([4.0, 4.0, 4.0]))) == [0.5, 0.5, 0.5]
    assert list(normalize_minmax(np.array([9.0]), equal_value=0.5)) == [0.5]
    assert normalize_minmax(np.array([])).size == 0


def test_score_is_sum_of_normalized_components_with_unit_weights(env):
    a = env.add("a", "planning a valentine party at the cafe", importance=8)
    b = env.add("a", "desk is idle", importance=1, created=T0 + hours(1))
    r = Retriever(env.store, env.embedder, paper())
    cands = r.score([a, b], "valentine party", T0 + hours(2))
    for c in cands:
        assert c.score == pytest.approx(c.norm_recency + c.norm_importance + c.norm_relevance)
        for v in (c.norm_recency, c.norm_importance, c.norm_relevance):
            assert 0.0 <= v <= 1.0 and not math.isnan(v)


def test_weights_change_the_ranking():
    emb = FixedEmbedder({"q": [1, 0, 0], "relevant but trivial": [1, 0, 0], "important but unrelated": [0, 1, 0]})
    env = Env(emb)
    rel = env.add("a", "relevant but trivial", importance=1)
    imp = env.add("a", "important but unrelated", importance=10)
    now = T0 + hours(1)
    by_relevance = Retriever(env.store, env.embedder, paper(weights=Weights(0, 0, 1))).score([rel, imp], "q", now)
    by_importance = Retriever(env.store, env.embedder, paper(weights=Weights(0, 1, 0))).score([rel, imp], "q", now)
    assert by_relevance[0].memory.id == rel.id
    assert by_importance[0].memory.id == imp.id


def test_negative_cosine_normalizes_without_nan():
    emb = FixedEmbedder({"q": [1, 0, 0], "same": [1, 0, 0], "opposite": [-1, 0, 0], "orthogonal": [0, 1, 0]})
    env = Env(emb)
    ms = [env.add("a", t) for t in ("same", "opposite", "orthogonal")]
    cands = {c.memory.description: c for c in Retriever(env.store, env.embedder, paper()).score(ms, "q", T0)}
    assert cands["opposite"].raw_relevance == pytest.approx(-1.0)
    assert cands["opposite"].norm_relevance == pytest.approx(0.0)
    assert cands["orthogonal"].norm_relevance == pytest.approx(0.5)
    assert cands["same"].norm_relevance == pytest.approx(1.0)


def test_zero_norm_embeddings_give_zero_cosine_and_are_flagged():
    sims, zero = cosine_to(np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]), np.array([1.0, 0.0, 0.0]))
    assert list(sims) == [0.0, 1.0] and list(zero) == [True, False]
    sims2, zero2 = cosine_to(np.array([[1.0, 0.0, 0.0]]), np.zeros(3))
    assert list(sims2) == [0.0] and list(zero2) == [True]
    env = Env(FixedEmbedder({"q": [1, 0, 0]}))  # unknown texts embed to zero vectors
    m = env.add("a", "unknown text")
    [c] = Retriever(env.store, env.embedder, paper()).score([m], "q", T0)
    assert c.zero_norm and c.raw_relevance == 0.0 and not math.isnan(c.score)


def test_no_memories_returns_empty(env):
    res = Retriever(env.store, env.embedder, paper()).retrieve("nobody", "anything", T0)
    assert res.candidates == [] and res.delivered == [] and res.used_tokens == 0


def test_ties_are_broken_deterministically():
    emb = FixedEmbedder({"q": [1, 0, 0], "twin one": [0, 1, 0], "twin two": [0, 1, 0]})
    env = Env(emb)
    a = env.add("a", "twin one", importance=5)
    b = env.add("a", "twin two", importance=5)
    r = Retriever(env.store, env.embedder, paper())
    order1 = [c.memory.id for c in r.score([a, b], "q", T0)]
    order2 = [c.memory.id for c in r.score([b, a], "q", T0)]
    assert order1 == order2 == sorted([a.id, b.id])  # same score, access, creation → id ascending


def test_prefix_selection_under_token_budget(env):
    long = "x" * 400  # ~100 tokens at 4 chars/token
    m1 = env.add("a", "valentine party planning " + long, importance=10, created=T0 + hours(2))
    m2 = env.add("a", "valentine party " + "y" * 400, importance=9, created=T0 + hours(1))
    m3 = env.add("a", "a short note about the party", importance=8, created=T0)
    r = Retriever(env.store, env.embedder, paper(budget_tokens=120))
    res = r.retrieve("a", "valentine party", T0 + hours(3))
    ranked = [c.memory.id for c in res.candidates]
    assert ranked[0] == m1.id
    # Prefix policy: the second memory does not fit, so selection stops there even though a
    # later, shorter memory would have fit.
    assert [m.id for m in res.delivered] == [m1.id]
    assert m3.id in ranked and m2.id in ranked
    assert res.used_tokens <= 120


def test_item_cap(env):
    for i in range(5):
        env.add("a", f"memory number {i} about coffee")
    res = Retriever(env.store, env.embedder, paper(max_items=2)).retrieve("a", "coffee", T0 + hours(1))
    assert len(res.delivered) == 2


def test_access_time_updates_only_delivered_and_after_scoring(env):
    ms = [env.add("a", f"talking about the election {i}", importance=i + 1) for i in range(4)]
    now = T0 + hours(5)
    r = Retriever(env.store, env.embedder, paper(max_items=2))
    res = r.retrieve("a", "election", now)
    delivered = {m.id for m in res.delivered}
    assert len(delivered) == 2
    for m in ms:
        stored = env.store.get(m.id)
        if m.id in delivered:
            assert stored.last_accessed_at == now
        else:
            assert stored.last_accessed_at == T0
    # Raw recency in the trace reflects pre-update access times (scored before touching).
    for c in res.candidates:
        assert c.raw_recency == pytest.approx(0.995**5)


def test_no_access_update_when_not_committed(env):
    m = env.add("a", "a quiet walk in the park")
    Retriever(env.store, env.embedder, paper()).retrieve("a", "park", T0 + hours(3), commit_access=False)
    assert env.store.get(m.id).last_accessed_at == T0


def test_future_memories_are_ineligible(env):
    past = env.add("a", "ate breakfast", created=T0)
    future = env.add("a", "hung decorations", created=T0 + hours(30))
    res = Retriever(env.store, env.embedder, paper()).retrieve("a", "decorations", T0 + hours(1))
    assert [c.memory.id for c in res.candidates] == [past.id]
    assert {"id": future.id, "reason": "created after query time"} in res.excluded


def test_kind_mask_excludes_types(env):
    obs = env.add("a", "saw Maria at the cafe")
    env.add("a", "Maria is a loyal friend", kind=MemoryKind.REFLECTION, origin=MemoryOrigin.INFERENCE)
    env.add("a", "invite Maria to the party", kind=MemoryKind.PLAN, origin=MemoryOrigin.INTENTION)
    res = Retriever(env.store, env.embedder, paper()).retrieve("a", "Maria", T0, kinds=[MemoryKind.OBSERVATION])
    assert [c.memory.id for c in res.candidates] == [obs.id]


def test_compat_recency_uses_positions_and_favors_oldest_access(env):
    old = env.add("a", "oldest access", created=T0)
    mid = env.add("a", "middle access", created=T0 + hours(1))
    new = env.add("a", "newest access", created=T0 + hours(2))
    r = Retriever(env.store, env.embedder, RetrievalSettings(mode="released_code", budget_tokens=None, max_items=None))
    cands = {c.memory.id: c for c in r.score([new, old, mid], "access", T0 + hours(3))}
    assert cands[old.id].access_position == 1 and cands[old.id].raw_recency == pytest.approx(0.995)
    assert cands[new.id].access_position == 3 and cands[new.id].raw_recency == pytest.approx(0.995**3)
    assert cands[old.id].norm_recency == 1.0 and cands[new.id].norm_recency == 0.0
    # Paper mode orders the same memories the opposite way.
    p = {c.memory.id: c for c in Retriever(env.store, env.embedder, paper()).score([new, old, mid], "access", T0 + hours(3))}
    assert p[new.id].norm_recency == 1.0 and p[old.id].norm_recency == 0.0


def test_compat_weights_and_idle_filter(env):
    env.add("a", "bed is idle", importance=1)
    m = env.add("a", "drinking coffee with Klaus", importance=4)
    n = env.add("a", "writing in her journal", importance=2, created=T0 + hours(1))
    r = Retriever(env.store, env.embedder, RetrievalSettings(mode="released_code", budget_tokens=None, max_items=None))
    res = r.retrieve("a", "coffee", T0 + hours(2))
    assert {c.memory.id for c in res.candidates} == {m.id, n.id}
    assert any("idle" in x["reason"] for x in res.excluded)
    for c in res.candidates:
        assert c.score == pytest.approx(0.5 * c.norm_recency + 2 * c.norm_importance + 3 * c.norm_relevance)


def test_explain_reports_component_differences(env):
    a = env.add("a", "Isabella is planning a Valentine's Day party", importance=8)
    b = env.add("a", "refrigerator is idle", importance=1)
    res = Retriever(env.store, env.embedder, paper()).retrieve("a", "Valentine's Day party", T0 + hours(1))
    why = res.explain(a.id, b.id)
    assert why["score_difference"] == pytest.approx(sum(why["difference"].values()))
    assert why["score_difference"] > 0 and a.id in why["verdict"]
    with pytest.raises(KeyError):
        res.explain(a.id, "missing")


def test_trace_is_persisted_with_components(env):
    traces = TraceStore(env.db, keep=1)
    env.add("a", "ordering decorations for the party", importance=6)
    env.add("a", "researching ideas for the party", importance=7)
    r = Retriever(env.store, env.embedder, paper(), trace_sink=traces.sink)
    res = r.retrieve("a", "party", T0 + hours(1), purpose="test")
    stored = traces.get(res.trace_id)
    assert stored["query"] == "party" and stored["purpose"] == "test"
    assert stored["candidates_total"] == 2 and stored["candidates_truncated"] == 1
    c = stored["candidates"][0]
    assert set(c["raw"]) == {"recency", "importance", "relevance"} and "normalized" in c
    assert stored["delivered"] == [m.id for m in res.delivered]


def test_keyword_lookup_matches_subject_or_object(env):
    hit = env.add("a", "Klaus Mueller is reading", subject="Klaus Mueller", predicate="is", object="reading")
    env.add("a", "Maria is streaming", subject="Maria Lopez", predicate="is", object="streaming")
    assert [m.id for m in keyword_lookup(env.store, "a", ["Klaus Mueller", "is", "writing"])] == [hit.id]


def test_store_is_append_only_and_isolated_per_agent(env):
    env.add("a", "only for a")
    env.add("b", "only for b")
    assert [m.description for m in env.store.for_agent("a")] == ["only for a"]
    with pytest.raises(ValueError):
        env.store.add(owner_id="a", kind=MemoryKind.OBSERVATION, origin=MemoryOrigin.DIRECT_OBSERVATION,
                      description="  ", created_at=T0, importance=1, embedding_model="m")


def test_clone_does_not_touch_source(env):
    env.add("a", "a memory in the source")
    before = env.db.content_hash()
    clone = env.db.clone()
    from generative_agents.memory.store import MemoryStore
    MemoryStore(clone).touch(["a.m00001"], T0 + hours(9))
    assert env.db.content_hash() == before
    assert clone.content_hash() != before
    assert isinstance(clone, Database)
