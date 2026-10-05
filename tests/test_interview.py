"""Matched-history interviews: masks, summary isolation, side effects, interview clock (spec M-1 … M-5, N-5)."""

from __future__ import annotations

import hashlib
from datetime import datetime

import pytest

from eval_helpers import snapshot, toy_run
from generative_agents.evaluation.interview import InterviewSession, InterviewSpec, run_interviews
from generative_agents.memory.masks import CONDITIONS, FULL, NO_MEMORY, NO_REFLECTION, OBSERVATIONS_ONLY
from generative_agents.providers.embeddings import MockHashEmbedding
from generative_agents.providers.mock import MockLLM


def session(cfg, snap, mask, **kw):
    return InterviewSession(cfg, snap, ledger_path=None, scope="t", mask=mask, provider=MockLLM(seed=1), embedding_provider=MockHashEmbedding(128), **kw)


@pytest.mark.parametrize("mask", [FULL, NO_REFLECTION, OBSERVATIONS_ONLY, NO_MEMORY])
def test_masks_limit_retrieval_and_summary(tmp_path, mask):
    cfg, db, _, _ = toy_run()
    snap = snapshot(db, tmp_path / "s.sqlite")
    s = session(cfg, snap, mask)
    a = s.ask("klaus_mueller", "What do you think about the party?")
    assert set(a.retrieved_kinds) <= {k.value for k in mask.kinds}
    desc = s.description("klaus_mueller")
    assert desc.startswith("Name: Klaus Mueller")  # identical static identity in every condition
    if mask is NO_MEMORY:
        assert a.retrieved_ids == [] and "Notably" not in desc
    if mask in (NO_REFLECTION, OBSERVATIONS_ONLY, NO_MEMORY):
        assert "curious about the party" not in desc  # no reflection leaks through the summary
    if mask is OBSERVATIONS_ONLY:
        assert "plan for Monday" not in desc


def test_interviews_leave_the_snapshot_and_access_times_untouched(tmp_path):
    cfg, db, _, _ = toy_run()
    snap = snapshot(db, tmp_path / "s.sqlite")
    before = hashlib.sha256(snap.read_bytes()).hexdigest()
    s = session(cfg, snap, FULL)
    times = {r["id"]: r["last_accessed_at"] for r in s.db.query("SELECT id, last_accessed_at FROM memories")}
    first = s.ask("klaus_mueller", "Was there a Valentine's day party?")
    second = s.ask("klaus_mueller", "Was there a Valentine's day party?")
    assert first.retrieved_ids == second.retrieved_ids  # the first question did not change the second
    assert times == {r["id"]: r["last_accessed_at"] for r in s.db.query("SELECT id, last_accessed_at FROM memories")}
    s.close()
    assert hashlib.sha256(snap.read_bytes()).hexdigest() == before


def test_today_resolves_against_the_interview_clock(tmp_path):
    cfg, db, _, _ = toy_run()
    snap = snapshot(db, tmp_path / "s.sqlite")
    s = session(cfg, snap, FULL, reference_time=datetime(2023, 2, 14, 7, 30))
    s.ask("klaus_mueller", "What will you be doing at 6pm today?")
    prompt = s.rt.ledger.rows(task="interview")[0]["prompt"]
    assert "It is February 14, 2023, 7:30 am." in prompt and "Current Date: Tuesday February 14" in prompt


def test_run_interviews_writes_responses_and_refuses_a_human_condition(tmp_path):
    cfg, db, _, _ = toy_run()
    snap = snapshot(db, tmp_path / "s.sqlite")
    spec = InterviewSpec(run_dir=tmp_path, snapshot=snap, conditions=list(CONDITIONS), questions=["self_1", "memory_4", "reflections_3"], seed=2)
    out = run_interviews(spec, cfg, provider=MockLLM(seed=1), embedding_provider=MockHashEmbedding(128))
    assert len(out["rows"]) == 3 * 3 * 4
    m = out["manifest"]
    assert m["side_effects"]["snapshot_sha256_before"] == m["side_effects"]["snapshot_sha256_after"]
    assert (out["dir"] / "responses.csv").exists() and m["selections"]["klaus_mueller"]["bindings"]["frequent_1"]
    with pytest.raises(ValueError):
        run_interviews(InterviewSpec(run_dir=tmp_path, snapshot=snap, conditions=["human_crowdworker"]), cfg, provider=MockLLM(seed=1))
