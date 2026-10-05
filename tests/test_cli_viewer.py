"""CLI commands and the read-only viewer API on a small offline run (spec §13 CLI)."""

from __future__ import annotations

import json

import pytest

from generative_agents.cli import main

pytest.importorskip("fastapi")


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("cli") / "run1"
    args = [
        "run",
        "--run-dir",
        str(d),
        "--set",
        "scenario.population=[isabella_rodriguez, klaus_mueller]",
        "--set",
        "scenario.start=2023-02-13T09:00:00",
        "--set",
        "scenario.end=2023-02-13T09:20:00",
        "--set",
        "output.checkpoint_every_steps=30",
        "--set",
        "providers.embeddings.dims=128",
    ]
    assert main(args) == 0
    return d


def test_run_writes_manifest_snapshots_and_frames(run_dir):
    m = json.loads((run_dir / "manifest.json").read_text())
    assert m["status"] == "completed" and m["mode"] == "mock" and not m["research_grade"]
    assert (run_dir / "snapshots" / "initial.sqlite").exists() and (run_dir / "snapshots" / "final.sqlite").exists()


def test_doctor_reports_mock_fixtures(capsys):
    main(["doctor"])
    out = capsys.readouterr().out
    assert "mock fixture" in out and "scenario" in out


def test_replay_command_matches_without_model_calls(run_dir, capsys):
    assert main(["replay", "--run-dir", str(run_dir), "--out", str(run_dir.parent / "replayed")]) == 0
    assert "state identical to the source: True" in capsys.readouterr().out


def test_inspect_memory_prints_components_and_explanation(run_dir, capsys):
    assert main(["inspect-memory", "--run-dir", str(run_dir), "--agent", "isabella_rodriguez", "--query", "Valentine's Day party", "--k", "5"]) == 0
    out = capsys.readouterr().out
    assert "why #1 outranked #2" in out and "rec" in out


def test_interview_evaluate_export_commands(run_dir, capsys):
    assert main(["interview", "--run-dir", str(run_dir), "--question", "self_1", "--question", "memory_4", "--name", "t"]) == 0
    assert (run_dir / "exports/interviews/t/responses.csv").exists()
    assert main(["interview", "--run-dir", str(run_dir), "--agent", "klaus_mueller", "--ask", "What did you do this morning?"]) == 0
    assert main(["export-blinded", "--run-dir", str(run_dir), "--name", "t", "--seed", "3"]) == 0
    assert main(["evaluate", "--run-dir", str(run_dir)]) == 0
    out = capsys.readouterr().out
    assert "not measured: attendance" in out
    assert main(["export", "--run-dir", str(run_dir)]) == 0
    assert (run_dir / "exports/run/run_report.md").read_text().startswith("# Run")


def test_live_run_requires_confirmation(tmp_path, capsys):
    code = main(["run", "--run-dir", str(tmp_path / "live"), "--set", "providers.llm.kind=anthropic", "--set", "providers.llm.model=claude-opus-5-5"])
    assert code == 2 and "Not started" in capsys.readouterr().out
    assert not (tmp_path / "live" / "state.sqlite").exists()


def test_viewer_api_is_read_only(run_dir):
    from fastapi.testclient import TestClient

    from generative_agents.viewer.app import create_app

    before = (run_dir / "state.sqlite").read_bytes()
    c = TestClient(create_app(run_dir))
    info = c.get("/api/run").json()
    assert info["mode"] == "mock" and info["evaluator_events"][0]["key"] == "valentines_party"
    assert c.get("/api/map").json()["width"] == 140
    frames = c.get(f"/api/frames?start=0&end={info['last_frame']}").json()["frames"]
    assert frames[0]["key"]
    agent = c.get("/api/agent/isabella_rodriguez?step=60").json()
    assert agent["identity"]["name"] == "Isabella Rodriguez" and agent["hours"]
    trace_id = agent["latest_trace"]
    assert "explain_top2" in c.get(f"/api/trace/{trace_id}").json()
    assert c.get("/api/timeline").json()["lanes"]
    assert c.get("/api/agent/nobody").status_code == 404
    assert c.get("/").status_code == 200
    assert (run_dir / "state.sqlite").read_bytes() == before
