"""Reflection extension: independent runs, disabled reflection paths, run-level summaries (spec R-1 … R-3)."""

from __future__ import annotations

import re

import yaml

from generative_agents.cognition.dialogue import DialogueEngine, Side
from generative_agents.cognition.reaction import ReactionEngine
from generative_agents.cognition.reflection import ReflectionEngine
from generative_agents.cognition.summary import SummaryService
from generative_agents.evaluation.experiment import Protocol, _permutation_p, estimate, execute, summarize
from generative_agents.evaluation.plots import strip_chart
from generative_agents.providers.mock import MockLLM
from generative_agents.schemas import MemoryOrigin
from helpers import ISABELLA, KLAUS, T, make_stack


def test_no_reflection_disables_every_reflective_path_but_keeps_transcript_summaries():
    cfg, db, rt, svc = make_stack(MockLLM(seed=3), ["architecture.reflection=false", "architecture.post_conversation_inferences=true"])
    assert not cfg.architecture.conversation_inferences_enabled()
    eng = ReflectionEngine(svc)
    svc.states.get(KLAUS.id).reflection_accumulator = 10_000
    assert not eng.should_reflect(KLAUS, T)
    summary = SummaryService(svc)
    conv = DialogueEngine(svc, summary, ReactionEngine(svc, summary)).run(
        Side(ISABELLA, "serving coffee", "Klaus is reading"), Side(KLAUS, "reading", "Isabella is serving coffee"), T, None
    )
    origins = {m.origin for m in svc.store.for_agent(KLAUS.id) if m.conversation_id == conv.id}
    assert MemoryOrigin.CONVERSATION in origins and MemoryOrigin.INFERENCE not in origins
    assert rt.ledger.rows(task="reflection_questions") == [] and rt.ledger.rows(task="conversation_inferences") == []


def protocol_file(tmp_path, base):
    p = tmp_path / "protocol.yaml"
    p.write_text(
        yaml.safe_dump(
            {
                "name": "tiny",
                "base_config": str(base),
                "question": "Does reflection change recall?",
                "conditions": {"full": ["architecture.reflection=true"], "no_reflection": ["architecture.reflection=false"]},
                "seeds": [1, 2],
                "output_dir": str(tmp_path / "experiments"),
            }
        )
    )
    return p


def base_config(tmp_path):
    b = tmp_path / "base.yaml"
    b.write_text(
        yaml.safe_dump(
            {
                "scenario": {
                    "path": "scenarios/pilot5/scenario.yaml",
                    "population": ["isabella_rodriguez", "klaus_mueller"],
                    "start": "2023-02-13T09:00:00",
                    "end": "2023-02-13T09:10:00",
                },
                "output": {"checkpoint_every_steps": 30},
                "providers": {"embeddings": {"kind": "mock-hash", "dims": 128}},
            }
        )
    )
    return b


def test_protocol_matches_seeds_and_plans_without_calling_models(tmp_path):
    proto = Protocol.load(protocol_file(tmp_path, base_config(tmp_path)))
    runs = proto.runs()
    assert [(r["condition"], r["seed"]) for r in runs] == [("full", 1), ("no_reflection", 1), ("full", 2), ("no_reflection", 2)]
    assert proto.config_for(runs[1]).architecture.reflection is False and proto.config_for(runs[1]).run.seed == 1
    est = estimate(proto)
    assert est["runs"] == 4 and "no measured pilot run" in est["basis"]


def test_execute_reports_every_run_and_missing_outcomes(tmp_path):
    proto = Protocol.load(protocol_file(tmp_path, base_config(tmp_path)))
    res = execute(proto)
    assert len(res["rows"]) == 4 and all(r["status"] == "completed" for r in res["rows"])
    assert all(r["invited_attendance_rate"] is None for r in res["rows"])  # the party window was never simulated
    assert {r["mode"] for r in res["rows"]} == {"mock"}
    root = tmp_path / "experiments" / "tiny"
    report = (root / "report.md").read_text()
    assert report.startswith("# Experiment: tiny") and "**MOCK RUNS.**" in report and "_Run modes: mock × 4._" in report
    assert "[full-s1](full-s1/exports/evaluation/report.md)" in report and (root / "full-s1" / "exports" / "evaluation" / "report.md").exists()
    assert "## By condition" in report and "| **Attendance among invited guests** | n/a | n/a |" in report and "| Cost (USD) | unpriced | unpriced |" in report
    for k in proto.primary_outcomes:
        assert (root / f"outcome_{k}.svg").exists() and f"(outcome_{k}.svg)" in report
    assert "mode" in (root / "runs.csv").read_text().splitlines()[0].split(",")
    summ = res["summary"]
    assert summ["unit"] == "run" and set(summ["conditions"]) == {"full", "no_reflection"}


def test_strip_chart_draws_every_run_on_a_fixed_axis():
    svg = strip_chart("recall", {"full": [("a", 1.0), ("b", 1.0), ("c", 0.6)], "no_reflection": [("d", 0.8)]})
    assert svg.count("<circle") == 4 and "full (n=3)" in svg and "no_reflection (n=1)" in svg
    cx = [float(x) for x in re.findall(r'<circle cx="([0-9.]+)"', svg)]
    assert cx[0] != cx[1]  # equal values are spread sideways, not hidden
    assert ">0.87<" in svg and ">0.80<" in svg  # condition means
    assert ">0<" in svg and ">1<" in svg  # the axis stays 0..1 for rates


def test_run_level_summary_statistics():
    proto = Protocol(name="p", base_config="x", conditions={"a": [], "b": []}, seeds=[1, 2, 3], primary_outcomes=["y"])
    rows = [
        {"run_id": f"{c}{i}", "condition": c, "status": "completed", "y": v}
        for c, vals in (("a", [0.8, 0.9, 1.0]), ("b", [0.1, 0.2, 0.3]))
        for i, v in enumerate(vals)
    ]
    rows.append({"run_id": "b9", "condition": "b", "status": "budget_exhausted", "stop_detail": "calls", "y": None})
    s = summarize(rows, proto)
    comp = s["comparisons"]["y"]
    assert comp["mean_difference"] == 0.7 and comp["permutation_p"] == 0.1  # 2 of 20 splits are this extreme
    assert comp["bootstrap_95ci"][0] > 0 and s["excluded"] == [{"run_id": "b9", "status": "budget_exhausted", "reason": "calls"}]
    assert _permutation_p([1.0], [1.0]) == 1.0
