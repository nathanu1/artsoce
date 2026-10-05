"""The reflection extension: independent runs with and without reflection (prompt §10; spec R-1 … R-3).

Each run is a whole simulation from the same authored world. Conditions differ only in
``architecture.reflection`` (which, when off, also disables post-conversation inferences;
observational conversation summaries stay). Runs are matched by seed across conditions;
with a hosted model this does not make the sampled behavior identical, and the report says so.

The run is the unit of analysis. Primary outcomes, fixed in the protocol before running:

* supported event recall: share of agents who claim the party/candidacy at the end *and*
  have received evidence of it in memory;
* attendance among invited guests (host excluded).

Also reported: exposure and invitation counts, unsupported claims, calls, tokens, cost (when
priced) and runtime. Failed and budget-truncated runs stay in the table with their reason.
Five runs per condition are exploratory; intervals and p-values are descriptive.

``plan`` and ``estimate`` never call a model. ``execute`` runs only when called explicitly.
"""

from __future__ import annotations

import json
import random
import statistics
import time
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any

import yaml

from ..config import apply_overrides, load_raw, repo_path
from .interview import write_csv

PRIMARY = ("supported_party_recall", "supported_candidacy_recall", "invited_attendance_rate")


@dataclass
class Protocol:
    name: str
    base_config: str
    conditions: dict[str, list[str]]
    seeds: list[int]
    question: str = ""
    primary_outcomes: list[str] = field(default_factory=lambda: list(PRIMARY))
    evaluate_relationships: bool = False
    min_minutes: float = 10.0
    output_dir: str = "runs/experiments"
    path: str | None = None

    @classmethod
    def load(cls, path: str | Path) -> Protocol:
        p = Path(path) if Path(path).exists() else repo_path(str(path))
        d = yaml.safe_load(p.read_text())
        return cls(
            name=d["name"],
            base_config=d["base_config"],
            conditions={k: list(v or []) for k, v in d["conditions"].items()},
            seeds=list(d["seeds"]),
            question=d.get("question", ""),
            primary_outcomes=list(d.get("primary_outcomes", PRIMARY)),
            evaluate_relationships=bool(d.get("evaluate_relationships", False)),
            min_minutes=float(d.get("min_minutes", 10.0)),
            output_dir=d.get("output_dir", "runs/experiments"),
            path=str(p),
        )

    def root(self) -> Path:
        return repo_path(self.output_dir) / self.name

    def runs(self) -> list[dict[str, Any]]:
        return [
            {"condition": c, "seed": s, "run_id": f"{c}-s{s}", "overrides": [*ov, f"run.seed={s}", f"run.name={self.name}-{c}-s{s}"]}
            for s in self.seeds
            for c, ov in self.conditions.items()
        ]

    def config_for(self, run: dict[str, Any]) -> Any:
        from ..config import GAConfig

        raw = load_raw(self.base_config)
        return GAConfig.model_validate(apply_overrides(raw, run["overrides"]))


def estimate(protocol: Protocol, measured_run: str | Path | None = None) -> dict[str, Any]:
    """Project calls and tokens from a measured pilot run; never invents prices."""

    runs = protocol.runs()
    cfg = protocol.config_for(runs[0])
    out: dict[str, Any] = {
        "runs": len(runs),
        "mode": cfg.run_mode,
        "limits_per_run": cfg.budget.model_dump(),
        "basis": None,
    }
    if measured_run is None:
        out["basis"] = "no measured pilot run; run one condition once and pass --measured-run to project usage"
        return out
    m = json.loads((Path(measured_run) / "manifest.json").read_text())
    led = m["ledger"]
    out["basis"] = f"measured run {m['run_id']} ({m['mode']}, status {m['status']}, sim time {m['sim_time']})"
    per = {"calls": led.get("calls") or 0, "input_tokens": led.get("input_tokens") or 0, "output_tokens": led.get("output_tokens") or 0}
    out["per_run_measured"] = per
    out["total_projected"] = {k: v * len(runs) for k, v in per.items()}
    cost = m["budget"]["usage"].get("cost_usd")
    priced = m["budget"]["usage"].get("unpriced_calls", 1) == 0 and cost is not None
    out["cost_projected_usd"] = round(cost * len(runs), 2) if priced and cost else None
    if not priced:
        out["cost_note"] = "unpriced: configure budget.pricing_file with current published prices to project cost"
    return out


def run_outcomes(run_dir: Path, evaluation: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    final = evaluation.get("snapshots", {}).get("final", {})
    diff = final.get("diffusion", {})
    party = diff.get("valentines_party", {})
    cand = diff.get("mayor_candidacy", {})
    att = evaluation.get("attendance") or {}
    inv = att.get("among_invited", {}) if att else {}
    usage = manifest.get("budget", {}).get("usage", {})
    return {
        "supported_party_recall": round(party["supported_aware"] / party["n"], 3) if party.get("n") else None,
        "supported_candidacy_recall": round(cand["supported_aware"] / cand["n"], 3) if cand.get("n") else None,
        "invited_attendance_rate": inv.get("rate"),
        "invited": inv.get("n"),
        "invited_attended": inv.get("attended"),
        "exposed_party": (att.get("among_exposed") or {}).get("n") if att else None,
        "unsupported_claims": (party.get("claimed_unsupported") or 0) + (cand.get("claimed_unsupported") or 0) if party or cand else None,
        "calls": manifest.get("ledger", {}).get("calls"),
        "input_tokens": manifest.get("ledger", {}).get("input_tokens"),
        "output_tokens": manifest.get("ledger", {}).get("output_tokens"),
        "cost_usd": usage.get("cost_usd") if usage.get("unpriced_calls", 1) == 0 else None,
        "runtime_s": round(usage.get("runtime_s", 0.0), 1),
    }


def execute(protocol: Protocol, *, provider_factory: Any = None, embedding_factory: Any = None, progress: Any = None) -> dict[str, Any]:
    from ..simulation.engine import Simulation, save_config
    from .evaluate import evaluate_run

    root = protocol.root()
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for run in protocol.runs():
        cfg = protocol.config_for(run)
        run_dir = root / run["run_id"]
        t0 = time.time()
        row: dict[str, Any] = {"condition": run["condition"], "seed": run["seed"], "run_id": run["run_id"], "run_dir": str(run_dir)}
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
            if not (run_dir / "config.yaml").exists():
                save_config(cfg, run_dir)
            sim = Simulation(
                cfg,
                run_dir,
                provider=provider_factory(run) if provider_factory else None,
                embedding_provider=embedding_factory(run) if embedding_factory else None,
            )
            status = sim.status if sim.status == "completed" else sim.run()
            sim.close()
            row["status"] = status
            manifest = json.loads((run_dir / "manifest.json").read_text())
            row["stop_detail"] = (manifest.get("stop_detail") or {}).get("detail")
            if status == "completed":
                ev = evaluate_run(
                    run_dir,
                    cfg,
                    relationships=protocol.evaluate_relationships,
                    min_minutes=protocol.min_minutes,
                    provider=provider_factory(run) if provider_factory else None,
                    embedding_provider=embedding_factory(run) if embedding_factory else None,
                )
                row.update(run_outcomes(run_dir, ev, manifest))
            else:
                row.update({k: None for k in PRIMARY})
        except Exception as exc:  # recorded, never hidden
            row["status"] = "error"
            row["stop_detail"] = f"{type(exc).__name__}: {exc}"
        row["wall_s"] = round(time.time() - t0, 1)
        rows.append(row)
        if progress:
            progress(row)
    summary = summarize(rows, protocol)
    write_csv(root / "runs.csv", rows, list(rows[0].keys()) if rows else [])
    (root / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    (root / "report.md").write_text(render(protocol, rows, summary))
    return {"rows": rows, "summary": summary, "dir": str(root)}


def _bootstrap_diff(a: list[float], b: list[float], seed: int = 0, n: int = 2000) -> tuple[float, float] | None:
    if len(a) < 2 or len(b) < 2:
        return None
    rng = random.Random(seed)
    diffs = sorted(statistics.mean(rng.choices(a, k=len(a))) - statistics.mean(rng.choices(b, k=len(b))) for _ in range(n))
    return (round(diffs[int(0.025 * n)], 3), round(diffs[int(0.975 * n) - 1], 3))


def _permutation_p(a: list[float], b: list[float]) -> float | None:
    """Exact two-sided permutation test on the difference in means (small n only)."""

    if not a or not b or len(a) + len(b) > 16:
        return None
    pooled = a + b
    obs = abs(statistics.mean(a) - statistics.mean(b))
    count = total = 0
    for idx in combinations(range(len(pooled)), len(a)):
        sa = [pooled[i] for i in idx]
        sb = [pooled[i] for i in range(len(pooled)) if i not in idx]
        total += 1
        if abs(statistics.mean(sa) - statistics.mean(sb)) >= obs - 1e-12:
            count += 1
    return round(count / total, 4)


def summarize(rows: list[dict[str, Any]], protocol: Protocol) -> dict[str, Any]:
    conds = list(protocol.conditions)
    out: dict[str, Any] = {"protocol": protocol.name, "unit": "run", "conditions": {}, "comparisons": {}, "excluded": []}
    for c in conds:
        rs = [r for r in rows if r["condition"] == c]
        out["conditions"][c] = {"runs": len(rs), "completed": len([r for r in rs if r.get("status") == "completed"]), "outcomes": {}}
        for k in (*protocol.primary_outcomes, "unsupported_claims", "calls", "input_tokens", "output_tokens", "runtime_s"):
            vals = [r[k] for r in rs if r.get(k) is not None]
            out["conditions"][c]["outcomes"][k] = (
                {
                    "n": len(vals),
                    "mean": round(statistics.mean(vals), 3),
                    "sd": round(statistics.stdev(vals), 3) if len(vals) > 1 else None,
                    "median": statistics.median(vals),
                    "min": min(vals),
                    "max": max(vals),
                }
                if vals
                else {"n": 0}
            )
    out["excluded"] = [{"run_id": r["run_id"], "status": r.get("status"), "reason": r.get("stop_detail")} for r in rows if r.get("status") != "completed"]
    if len(conds) == 2:
        a, b = conds
        for k in protocol.primary_outcomes:
            va = [r[k] for r in rows if r["condition"] == a and r.get(k) is not None]
            vb = [r[k] for r in rows if r["condition"] == b and r.get(k) is not None]
            out["comparisons"][k] = {
                "difference": f"{a} - {b}",
                "mean_difference": round(statistics.mean(va) - statistics.mean(vb), 3) if va and vb else None,
                "bootstrap_95ci": _bootstrap_diff(va, vb),
                "permutation_p": _permutation_p(va, vb),
                "n": [len(va), len(vb)],
                "note": "exploratory; run-level; not powered",
            }
    return out


def render(protocol: Protocol, rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    modes = sorted({str(r.get("mode", "")) for r in rows})
    lines = [f"# Experiment: {protocol.name}", "", protocol.question or "", ""]
    cfg = protocol.config_for(protocol.runs()[0]) if rows else None
    if cfg is not None and cfg.run_mode != "live":
        lines += [f"> **{cfg.run_mode.upper()} RUNS.** These numbers exercise the pipeline with the offline mock; they say nothing about reflection.", ""]
    lines += [
        "Conditions differ only in `architecture.reflection`. Runs are matched by seed; a hosted model does not reproduce identical samples, so matching is of the initial world, not of the randomness.",
        "",
        "| Run | Condition | Seed | Status | Party recall (supported) | Candidacy recall (supported) | Invited who attended | Unsupported claims | Calls | Runtime (s) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        inv = f"{r.get('invited_attended')}/{r.get('invited')}" if r.get("invited") is not None else "n/a"
        lines.append(
            f"| {r['run_id']} | {r['condition']} | {r['seed']} | {r.get('status')} | {r.get('supported_party_recall')} | {r.get('supported_candidacy_recall')} | {inv} | {r.get('unsupported_claims')} | {r.get('calls')} | {r.get('runtime_s')} |"
        )
    lines += ["", "## Comparisons (exploratory)", ""]
    for k, v in summary.get("comparisons", {}).items():
        lines.append(
            f"* **{k}**: {v['difference']} = {v['mean_difference']} (bootstrap 95% CI {v['bootstrap_95ci']}, exact permutation p = {v['permutation_p']}, n = {v['n']})"
        )
    if summary.get("excluded"):
        lines += ["", "## Runs without outcomes", ""] + [f"* {e['run_id']}: {e['status']} — {e['reason']}" for e in summary["excluded"]]
    lines += ["", "_modes: " + ", ".join(m for m in modes if m) + "_", ""]
    return "\n".join(lines)
