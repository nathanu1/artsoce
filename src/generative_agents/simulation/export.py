"""``ga export``: portable files for one run (prompt §12).

* ``events.jsonl``, ``transcripts.jsonl``, ``retrieval_traces.jsonl``, ``model_calls.jsonl``
  (prompts and raw outputs as recorded; no credentials are ever stored);
* ``memories.csv``, ``plans.csv``, ``calls_by_task.csv``, ``checkpoints.csv``;
* ``manifest.json`` (copy) and ``run_report.md``.

Mock, replayed and live runs are labeled in every report.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Any

from ..db import Database
from ..providers.ledger import CallLedger


def _jsonl(path: Path, rows: list[dict[str, Any]]) -> int:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")
    return len(rows)


def _csv(path: Path, rows: list[dict[str, Any]], cols: list[str]) -> int:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in r.items()})
    return len(rows)


def export_run(run_dir: Path) -> dict[str, str]:
    db = Database(run_dir / "state.sqlite", read_only=True)
    out = run_dir / "exports" / "run"
    out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((run_dir / "manifest.json").read_text()) if (run_dir / "manifest.json").exists() else {}
    events = []
    for r in db.query("SELECT id, step, sim_time, type, agent_id, json FROM events ORDER BY id"):
        d = json.loads(r["json"])
        events.append({"id": r["id"], "step": r["step"], "sim_time": r["sim_time"], "type": r["type"], "agent_id": r["agent_id"], **d})
    n_events = _jsonl(out / "events.jsonl", events)
    convs = [json.loads(r["json"]) for r in db.query("SELECT json FROM conversations ORDER BY started_at, id")]
    n_conv = _jsonl(out / "transcripts.jsonl", convs)
    traces = []
    for r in db.query("SELECT id, agent_id, sim_time, purpose, json FROM retrieval_traces ORDER BY sim_time, id"):
        traces.append({"id": r["id"], **json.loads(r["json"])})
    n_tr = _jsonl(out / "retrieval_traces.jsonl", traces)
    mems = [
        dict(r)
        for r in db.query(
            "SELECT id, owner_id, seq, kind, origin, description, created_at, last_accessed_at, importance, depth, evidence_json, conversation_id, speaker_id, seed FROM memories ORDER BY owner_id, seq"
        )
    ]
    n_mem = _csv(out / "memories.csv", mems, list(mems[0].keys()) if mems else ["id"])
    plans = [json.loads(r["json"]) for r in db.query("SELECT json FROM plans ORDER BY agent_id, start, id")]
    n_plans = _csv(out / "plans.csv", plans, ["id", "agent_id", "level", "parent_id", "day", "start", "duration_min", "description", "status", "source"])
    cps = [
        {"step": r["step"], "sim_time": r["sim_time"], **json.loads(r["json"])} for r in db.query("SELECT step, sim_time, json FROM checkpoints ORDER BY step")
    ]
    _csv(out / "checkpoints.csv", cps, ["step", "sim_time", "note"])
    run_id = db.get_meta("run_id") or run_dir.name
    calls: list[dict[str, Any]] = []
    by_task: list[dict[str, Any]] = []
    ledger_path = run_dir / "provider.sqlite"
    if ledger_path.exists():
        led = CallLedger(ledger_path, scope=run_id)
        for row in led.rows():
            calls.append(
                {
                    k: row[k]
                    for k in (
                        "id",
                        "step",
                        "sim_time",
                        "task",
                        "template_id",
                        "agent_id",
                        "purpose",
                        "model",
                        "served_model",
                        "status",
                        "attempt_kind",
                        "input_tokens",
                        "output_tokens",
                        "cost_usd",
                        "system",
                        "prompt",
                        "raw_output",
                        "error",
                    )
                    if k in row
                }
            )
        tot = led.totals()
        by_task = [{"task": k, **v} for k, v in tot["by_task"].items()]
        led.close()
    n_calls = _jsonl(out / "model_calls.jsonl", calls)
    _csv(out / "calls_by_task.csv", by_task, ["task", "calls", "input_tokens", "output_tokens"])
    if (run_dir / "manifest.json").exists():
        shutil.copy(run_dir / "manifest.json", out / "manifest.json")
    (out / "run_report.md").write_text(_report(run_dir, manifest, db, events, convs, by_task))
    db.close()
    return {
        "dir": str(out),
        "events": str(n_events),
        "transcripts": str(n_conv),
        "traces": str(n_tr),
        "memories": str(n_mem),
        "plans": str(n_plans),
        "model_calls": str(n_calls),
    }


def _report(run_dir: Path, m: dict[str, Any], db: Database, events: list[dict[str, Any]], convs: list[dict[str, Any]], by_task: list[dict[str, Any]]) -> str:
    mode = str(m.get("mode", "?")).upper()
    lines = [f"# Run {m.get('run_id', run_dir.name)}", ""]
    if m.get("mock_llm") or m.get("mock_embeddings"):
        lines += ["> **MOCK RUN.** Offline fixtures (mock model and/or hash embeddings). Structural demonstration only; not a research result.", ""]
    elif m.get("replay_of"):
        lines += [f"> **REPLAY** of {m['replay_of']}. No model was called.", ""]
    lines += [
        f"* Mode: {mode}; status: `{m.get('status')}`; simulated until {m.get('sim_time')} (step {m.get('next_step')})",
        f"* Scenario: {m.get('scenario', {}).get('name')} with {len(m.get('scenario', {}).get('agents', []))} agents; seed policy {m.get('scenario', {}).get('candidacy_seed_policy')}",
        f"* Model: {m.get('llm')}; embeddings: {m.get('embeddings', {}).get('model_key')}",
        f"* Calls: {m.get('ledger', {}).get('calls')}; tokens in/out {m.get('ledger', {}).get('input_tokens')}/{m.get('ledger', {}).get('output_tokens')}; cost {m.get('ledger', {}).get('cost_usd') or 'unpriced'}",
        f"* Code: {m.get('code', {}).get('git_commit')}",
        "",
        "## Activity",
        "",
        "| Agent | Memories | Reflections | Conversations | Actions | Action failures | Constraint refusals |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    agents = [r["id"] for r in db.query("SELECT id FROM agents ORDER BY order_index")]
    for aid in agents:
        mem = db.one("SELECT COUNT(*) n FROM memories WHERE owner_id=?", (aid,))["n"]
        refl = db.one("SELECT COUNT(*) n FROM memories WHERE owner_id=? AND kind='reflection'", (aid,))["n"]
        conv = sum(1 for c in convs if aid in c["participants"])
        acts = sum(1 for e in events if e["type"] == "action" and e["agent_id"] == aid)
        fails = sum(1 for e in events if e["type"] == "action_failure" and e["agent_id"] == aid)
        cons = sum(1 for e in events if e["type"] == "constraint" and e["agent_id"] == aid)
        lines.append(f"| {aid} | {mem} | {refl} | {conv} | {acts} | {fails} | {cons} |")
    lines += ["", "## Model calls by task", "", "| Task | Calls | Input tokens | Output tokens |", "| --- | --- | --- | --- |"]
    lines += [f"| {r['task']} | {r['calls']} | {r['input_tokens']} | {r['output_tokens']} |" for r in by_task]
    lines += ["", "## Sample conversations", ""]
    for c in convs[:3]:
        lines.append(f"**{c['id']}** {', '.join(c['participants'])} at {c['started_at']} ({c.get('status')}): {c.get('summary') or ''}")
        lines += [f"> {u['speaker_id']}: {u['text']}" for u in c.get("utterances", [])[:6]]
        lines.append("")
    lines += [
        "Files: `events.jsonl`, `transcripts.jsonl`, `retrieval_traces.jsonl`, `model_calls.jsonl`, `memories.csv`, `plans.csv`, `calls_by_task.csv`, `checkpoints.csv`, `manifest.json`.",
        "",
    ]
    lines += ["These are simulated characters; plausibility here does not establish validity for real people.", ""]
    return "\n".join(lines)
