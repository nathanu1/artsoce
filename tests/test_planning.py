"""Hierarchical planning: validation, JIT decomposition, replanning, midnight (spec G-1 … G-8)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from generative_agents.cognition.planning import Planner, PlanStore, is_sleep
from generative_agents.cognition.summary import SummaryService
from generative_agents.providers.mock import MockLLM, ScriptedLLM
from generative_agents.schemas import MemoryKind, PlanLevel, PlanStatus
from helpers import ISABELLA, KLAUS, make_stack

D0 = datetime(2023, 2, 13, 0, 0)


def planner_for(provider=None, overrides=None):
    cfg, db, rt, svc = make_stack(provider or MockLLM(seed=11), overrides)
    plans = PlanStore(db)
    return Planner(svc, SummaryService(svc), plans), plans, rt, svc


def test_day_plan_and_hour_blocks_cover_the_day_contiguously():
    planner, plans, rt, svc = planner_for()
    assert planner.ensure_day(ISABELLA, D0)
    blocks = plans.items(ISABELLA.id, day="2023-02-13", level=PlanLevel.HOUR)
    assert blocks[0].start == D0
    for a, b in zip(blocks, blocks[1:], strict=False):
        assert a.end == b.start and a.description != b.description  # contiguous, merged
    assert blocks[-1].end == D0 + timedelta(days=1)
    day = plans.items(ISABELLA.id, day="2023-02-13", level=PlanLevel.DAY)
    assert len(day) == 1 and day[0].memory_id
    mems = svc.store.for_agent(ISABELLA.id, kinds=[MemoryKind.PLAN])
    assert any(m.description.startswith("This is Isabella Rodriguez's plan for Monday February 13") for m in mems)
    assert not svc.store.for_agent(KLAUS.id)  # plans live only in the planner's own stream
    assert planner.ensure_day(ISABELLA, D0 + timedelta(hours=3))  # idempotent
    assert len(rt.ledger.rows(task="day_plan")) == 1


def test_invalid_day_plan_is_repaired_once():
    bad = {"wake_up_time": "6am", "items": [{"time": "07:00", "activity": "wake up"}]}
    planner, plans, rt, _ = planner_for(ScriptedLLM({"day_plan": [bad]}, fallback=MockLLM(seed=11)))
    assert planner.ensure_day(ISABELLA, D0)
    calls = rt.ledger.rows(task="day_plan")
    assert len(calls) == 2 and calls[0]["status"] == "invalid" and calls[1]["status"] == "ok"


def test_failed_day_plan_leaves_no_plan_and_retries_later():
    bad = {"wake_up_time": "x", "items": []}
    planner, plans, rt, svc = planner_for(ScriptedLLM({"day_plan": [bad, bad]}, fallback=MockLLM(seed=11)))
    assert not planner.ensure_day(ISABELLA, D0)
    assert plans.items(ISABELLA.id) == []  # nothing invented
    assert planner.current_task(ISABELLA, D0 + timedelta(hours=9)) is None
    assert [e["level"] for e in svc.events.query("plan_failure")] == ["day"]
    assert not planner.ensure_day(ISABELLA, D0 + timedelta(minutes=10))  # cooldown: no new call
    assert len(rt.ledger.rows(task="day_plan")) == 2
    assert planner.ensure_day(ISABELLA, D0 + timedelta(minutes=31))  # script exhausted -> mock answers


def test_tasks_are_decomposed_just_in_time_for_the_current_window():
    planner, plans, rt, _ = planner_for()
    planner.ensure_day(KLAUS, D0)
    t = D0 + timedelta(hours=9, minutes=20)
    task = planner.current_task(KLAUS, t)
    assert task is not None and task.start <= t < task.end
    tasks = plans.items(KLAUS.id, level=PlanLevel.TASK)
    block = plans.get(task.parent_id)
    ws = block.start + timedelta(hours=int((t - block.start).total_seconds() // 3600))
    window = [x for x in tasks if x.parent_id == block.id]
    assert window[0].start == ws and sum(x.duration_min for x in window) == min(60, int((block.end - ws).total_seconds() // 60))
    assert all(5 <= x.duration_min <= 15 for x in window)
    for a, b in zip(window, window[1:], strict=False):
        assert a.end == b.start
    n = len(rt.ledger.rows(task="decompose"))
    assert planner.current_task(KLAUS, t + timedelta(minutes=1)).id in {x.id for x in window}
    assert len(rt.ledger.rows(task="decompose")) == n  # no repeated decomposition inside the window
    assert all(x.end <= ws + timedelta(hours=1) for x in tasks)  # later windows not decomposed yet


def test_sleep_is_not_decomposed():
    planner, plans, rt, _ = planner_for()
    planner.ensure_day(ISABELLA, D0)
    task = planner.current_task(ISABELLA, D0 + timedelta(hours=2))
    assert task is not None and is_sleep(task.description) and task.source == "block"
    assert rt.ledger.rows(task="decompose") == []


def test_insert_supersedes_overlaps_and_replans_rest_of_window():
    planner, plans, rt, svc = planner_for()
    planner.ensure_day(KLAUS, D0)
    t = D0 + timedelta(hours=9, minutes=7, seconds=40)
    first = planner.current_task(KLAUS, t)
    inserted = planner.insert(KLAUS, t, "talk to Isabella about her party", 12, source="conversation")
    assert inserted.start == t.replace(second=0) and inserted.duration_min == 12
    assert planner.current_task(KLAUS, t).id == inserted.id
    old = plans.get(first.id)
    assert old.status in (PlanStatus.DONE, PlanStatus.SUPERSEDED)
    block = plans.get(inserted.parent_id)
    ws, we = planner.window_of(block, t)
    active = [x for x in plans.items(KLAUS.id, level=PlanLevel.TASK) if x.status != PlanStatus.SUPERSEDED and x.end > t]
    covered = sorted(active, key=lambda x: x.start)
    assert covered[0].id == inserted.id
    assert covered[-1].end == we  # the regenerated rest ends exactly at the window end
    for a, b in zip(covered, covered[1:], strict=False):
        assert a.end == b.start
    assert len(rt.ledger.rows(task="replan")) == 1
    assert svc.events.query("replan")[0]["displaced"]


def test_wait_pauses_the_plan_without_replacing_it():
    planner, plans, rt, _ = planner_for()
    planner.ensure_day(KLAUS, D0)
    t = D0 + timedelta(hours=9, minutes=3)
    task = planner.current_task(KLAUS, t)
    wait = planner.insert(KLAUS, t, "waiting for the bathroom", 5, source="wait", displace=False)
    assert planner.current_task(KLAUS, t).id == wait.id
    planner.mark_done(wait.id, t + timedelta(minutes=5))
    later = planner.current_task(KLAUS, t + timedelta(minutes=5))
    if task.end > t + timedelta(minutes=5):
        assert later.id == task.id  # resumes the paused task
    assert plans.get(task.id).status != PlanStatus.SUPERSEDED


def test_midnight_boundary_spillover_and_next_day_plan():
    planner, plans, rt, _ = planner_for()
    planner.ensure_day(ISABELLA, D0)
    late = D0 + timedelta(hours=23, minutes=58)
    chat = planner.insert(ISABELLA, late, "chatting with Klaus Mueller", 10, source="conversation")
    nxt = D0 + timedelta(days=1)
    assert planner.ensure_day(ISABELLA, nxt)
    assert planner.current_task(ISABELLA, nxt + timedelta(minutes=5)).id == chat.id
    after = planner.current_task(ISABELLA, nxt + timedelta(minutes=8))
    assert after.id != chat.id and after.start == chat.end and after.day == "2023-02-14"
    assert len(rt.ledger.rows(task="day_plan")) == 2


def test_idempotent_completion():
    planner, plans, _, _ = planner_for()
    planner.ensure_day(KLAUS, D0)
    t = D0 + timedelta(hours=9, minutes=1)
    task = planner.current_task(KLAUS, t)
    planner.mark_done(task.id, t)  # not finished yet: no change
    assert plans.get(task.id).status == PlanStatus.PLANNED
    planner.mark_done(task.id, task.end)
    planner.mark_done(task.id, task.end + timedelta(minutes=1))
    assert plans.get(task.id).status == PlanStatus.DONE
    assert planner.current_task(KLAUS, task.end).id != task.id


@pytest.mark.parametrize("text,expected", [("sleeping", True), ("go to bed", True), ("take a nap", True), ("make the bed", False), ("have breakfast", False)])
def test_sleep_detection(text, expected):
    assert is_sleep(text) is expected
