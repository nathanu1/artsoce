"""``ga``: the command-line interface.

Every command is bounded and explicit. Nothing here launches a model call without being
asked: live runs print their limits and need ``--yes``; experiments only plan and estimate
unless ``--execute`` is given; ``replay`` never calls a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PAPER_SHA256 = "1b31e77fb24d25d7598f2c49e955d12a28b95a6dabad34acdac40f44bfb7a139"
DEFAULT_BANK = "configs/questions/appendix_b_reference.yaml"


def _print(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _cfg(args: argparse.Namespace):
    from .config import load_config

    return load_config(args.config, overrides=args.set)


def _progress_printer(every: int = 360):
    def cb(step: int, now: datetime) -> None:
        if step % every == 0:
            print(f"  step {step:>6}  {now:%a %d %b %H:%M}", flush=True)

    return cb


def _live_guard(cfg, yes: bool) -> bool:
    if cfg.run_mode != "live":
        return True
    b = cfg.budget
    if cfg.providers.llm.is_local():
        print(
            f"Local model {cfg.providers.llm.kind}:{cfg.providers.llm.model} (no API charges); population "
            f"{cfg.scenario.population or 'all agents in the scenario'}; {cfg.scenario.start} → {cfg.scenario.end}. "
            f"Limits: calls {b.max_calls}, runtime {b.max_runtime_s} s."
        )
        return True
    print(
        f"Live run with {cfg.providers.llm.kind}:{cfg.providers.llm.model}; population {cfg.scenario.population or 'all agents in the scenario'}; "
        f"{cfg.scenario.start} → {cfg.scenario.end}.\n"
        f"Limits: calls {b.max_calls}, input tokens {b.max_input_tokens}, output tokens {b.max_output_tokens}, runtime {b.max_runtime_s} s, cost {b.max_cost_usd} USD."
    )
    if not yes:
        print("Not started. Re-run with --yes to spend real API calls within these limits.")
        return False
    return True


# ---------------------------------------------------------------------- doctor
def cmd_doctor(args: argparse.Namespace) -> int:
    from .config import repo_path
    from .prompting import PromptRegistry
    from .providers.pricing import PriceTable
    from .scenario.audit import audit_scenario
    from .scenario.loader import load_scenario

    checks: list[tuple[str, str, str]] = []

    def add(name: str, status: str, detail: str = "") -> None:
        checks.append((status, name, detail))

    add("python", "ok" if sys.version_info >= (3, 11) else "fail", platform.python_version())
    try:
        cfg = _cfg(args)
        add("config", "ok", f"{args.config or 'defaults'} (mode {cfg.run_mode})")
    except Exception as exc:
        add("config", "fail", str(exc))
        return _report(checks)
    try:
        reg = PromptRegistry()
        add("prompt templates", "ok", f"{len(reg.tasks())} templates, versioned and hashed")
    except Exception as exc:
        add("prompt templates", "fail", str(exc))
    try:
        sc = load_scenario(repo_path(cfg.scenario.path), population=cfg.scenario.population, candidacy_seed_policy=cfg.scenario.candidacy_seed_policy)
        rep = audit_scenario(sc)
        add(
            "scenario",
            "ok" if rep["ok"] else "warn",
            f"{sc.name}: {len(sc.agent_ids)} agents; " + ("audit clean" if rep["ok"] else "; ".join(rep["issues"][:3])),
        )
    except Exception as exc:
        add("scenario", "fail", str(exc))
    llm = cfg.providers.llm
    if llm.kind == "mock":
        add("language model", "warn", "mock fixture: runs are structural demonstrations, not research results")
    elif llm.kind == "anthropic":
        ok_sdk = _importable("anthropic")
        key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        add(
            "language model",
            "ok" if ok_sdk and key else "fail",
            f"anthropic:{llm.model}; SDK {'installed' if ok_sdk else 'missing (pip install -e .[anthropic])'}; ANTHROPIC_API_KEY {'set' if key else 'not set'}",
        )
    elif llm.kind == "openai":
        ok_sdk = _importable("openai")
        key = bool(os.environ.get("OPENAI_API_KEY"))
        add(
            "language model",
            "ok" if ok_sdk and key else "fail",
            f"openai:{llm.model}; SDK {'installed' if ok_sdk else 'missing'}; OPENAI_API_KEY {'set' if key else 'not set'}",
        )
    emb = cfg.providers.embeddings
    if llm.kind == "ollama" or emb.kind == "ollama":
        _doctor_ollama(cfg, add)
    if llm.kind == "openai_compatible":
        add("language model", "ok", f"openai_compatible:{llm.model} at {llm.base_url or 'http://localhost:1234/v1'} (not probed; start the server first)")
    if emb.kind == "mock-hash":
        add("embeddings", "warn", "mock-hash fixture: lexical hashing, never semantic retrieval results")
    elif emb.kind == "openai":
        add("embeddings", "ok" if os.environ.get("OPENAI_API_KEY") and _importable("openai") else "fail", f"openai:{emb.model}")
    elif emb.kind == "ollama":
        pass  # checked with the server above
    elif emb.kind == "openai_compatible":
        add(
            "embeddings",
            "ok" if emb.dims else "warn",
            f"openai_compatible:{emb.model} ({'dims ' + str(emb.dims) if emb.dims else 'set dims so replays can rebuild the cache key'})",
        )
    else:
        add(
            "embeddings",
            "ok" if _importable("sentence_transformers") else "fail",
            f"sentence-transformers:{emb.model} ({emb.local_dir or 'download on first use'})",
        )
    if llm.is_local():
        add("pricing", "ok", "local model: no API charges (calls are recorded at 0 USD)")
    elif cfg.budget.pricing_file:
        try:
            pt = PriceTable.load(repo_path(cfg.budget.pricing_file))
            known = llm.model in pt.models
            add("pricing", "ok" if known else "warn", f"{cfg.budget.pricing_file} (as of {pt.as_of}); {'has' if known else 'no'} price for {llm.model}")
        except Exception as exc:
            add("pricing", "fail", str(exc))
    else:
        add("pricing", "warn", "no pricing file: cost is reported as unpriced (token counts only)")
    pdf = repo_path("docs/2304.03442v2.pdf")
    if pdf.exists():
        sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
        add(
            "paper PDF",
            "ok" if sha == PAPER_SHA256 else "warn",
            f"docs/2304.03442v2.pdf {'matches' if sha == PAPER_SHA256 else 'differs from'} the arXiv v2 hash",
        )
    else:
        add("paper PDF", "warn", "docs/2304.03442v2.pdf not present (git-ignored); the spec cites its page numbers")
    add(
        "viewer",
        "ok" if _importable("fastapi") and _importable("uvicorn") else "warn",
        "fastapi + uvicorn" if _importable("fastapi") else "install with pip install -e .[viewer]",
    )
    free = shutil.disk_usage(repo_path(".")).free / 1e9
    add("disk", "ok" if free > 2 else "warn", f"{free:.1f} GB free (the offline 25-agent two-day run used about 0.5 GB with snapshots)")
    return _report(checks)


def _doctor_ollama(cfg, add) -> None:
    from .providers.ollama_provider import ollama_status

    llm, emb = cfg.providers.llm, cfg.providers.embeddings
    wanted = [m for m, used in ((llm.model, llm.kind == "ollama"), (emb.model, emb.kind == "ollama")) if used]
    wanted += [o["model"] for o in llm.task_overrides.values() if llm.kind == "ollama" and o.get("model")]
    base = llm.base_url if llm.kind == "ollama" else emb.base_url
    st = ollama_status(base, list(dict.fromkeys(wanted)))
    if not st["reachable"]:
        add("ollama", "fail", f"not reachable at {st['base_url']}: start it with `ollama serve` (or open the Ollama app)")
        return
    add("ollama", "ok", f"server {st['version']} at {st['base_url']}")
    for model, info in st["present"].items():
        if info:
            add(f"model {model}", "ok", f"pulled; digest {str(info['digest'])[:19]}, {info['size'] / 1e9:.1f} GB" if info.get("size") else "pulled")
        else:
            add(f"model {model}", "fail", f"not pulled: run `ollama pull {model}`")
    if llm.kind == "ollama":
        add("context window", "ok", f"num_ctx {llm.num_ctx} (prompts here reach about 2,500 tokens; 4096 is the practical minimum)")


def _importable(mod: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(mod) is not None


def _report(checks: list[tuple[str, str, str]]) -> int:
    marks = {"ok": "ok  ", "warn": "WARN", "fail": "FAIL"}
    for status, name, detail in checks:
        print(f"[{marks[status]}] {name:<18} {detail}")
    return 1 if any(s == "fail" for s, _, _ in checks) else 0


# ---------------------------------------------------------------------- run / resume / replay
def cmd_run(args: argparse.Namespace) -> int:
    from .simulation.engine import Simulation, new_run_dir, save_config

    cfg = _cfg(args)
    if not _live_guard(cfg, args.yes):
        return 2
    run_dir = Path(args.run_dir) if args.run_dir else new_run_dir(cfg, args.run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    save_config(cfg, run_dir)
    if args.interventions:
        shutil.copy(args.interventions, run_dir / "interventions.yaml")
    sim = Simulation(cfg, run_dir)
    print(f"run {sim.run_id} ({cfg.run_mode}) → {run_dir}")
    until = datetime.fromisoformat(args.until) if args.until else None
    status = sim.run(until=until, max_steps=args.max_steps, progress=_progress_printer())
    _summary(sim, status)
    sim.close()
    return 0 if status in ("completed", "interrupted") else 1


def _summary(sim, status: str) -> None:
    led = sim.rt.ledger.totals()
    print(f"status: {status} at {sim.clock.now:%a %d %b %Y %H:%M:%S} (step {sim.clock.step})")
    print(
        f"model calls: {led['calls']} recorded ({sim.rt.budget.usage.cache_hits} served from the ledger), tokens in/out {led['input_tokens']}/{led['output_tokens']}"
    )
    detail = sim.db.get_meta("stop_detail")
    if detail and status not in ("completed",):
        print(f"stopped because: {detail.get('detail')}")
    print(f"next: ga evaluate --run-dir {sim.run_dir}   |   ga serve --run-dir {sim.run_dir}")


def cmd_resume(args: argparse.Namespace) -> int:
    from .simulation.engine import Simulation, load_run_config

    run_dir = Path(args.run_dir)
    cfg = load_run_config(run_dir, args.set)
    if not _live_guard(cfg, args.yes):
        return 2
    if args.set:
        (run_dir / f"config.resume-{datetime.now():%Y%m%d-%H%M%S}.yaml").write_text("\n".join(args.set) + "\n")
    sim = Simulation(cfg, run_dir)
    print(f"resuming {sim.run_id} from step {sim.clock.step} ({sim.clock.now})")
    status = sim.run(max_steps=args.max_steps, progress=_progress_printer())
    _summary(sim, status)
    sim.close()
    return 0 if status in ("completed", "interrupted") else 1


def cmd_replay(args: argparse.Namespace) -> int:
    from .db import Database
    from .simulation.engine import Simulation, load_run_config

    src = Path(args.run_dir)
    cfg = load_run_config(src)
    out = Path(args.out) if args.out else src.parent / f"{src.name}-replay"
    if out.exists() and any(out.iterdir()):
        print(f"{out} already exists; pass --out to choose another directory")
        return 2
    source_db = Database(src / "state.sqlite", read_only=True)
    target = int(source_db.get_meta("next_step", 0))
    tables = ("memories", "plans", "conversations", "agent_state", "spatial_memory", "world_objects")
    source_hash = source_db.content_hash(tables)
    source_db.close()
    sim = Simulation(cfg, out, replay_from=src)
    print(f"replaying {src.name} to step {target} from its ledger (no model calls) → {out}")
    status = sim.run(max_steps=target, progress=_progress_printer())
    same = sim.db.content_hash(tables) == source_hash
    print(f"replay status: {status}; state identical to the source: {same}")
    if status == "failed":
        print(f"diverged: {sim.db.get_meta('stop_detail')}")
    sim.close()
    return 0 if same else 1


# ---------------------------------------------------------------------- inspection
def cmd_inspect_memory(args: argparse.Namespace) -> int:
    from .cognition.summary import SummaryService  # noqa: F401  (import check)
    from .db import parse_iso
    from .evaluation.interview import InterviewSession
    from .memory.evidence import evidence_tree
    from .memory.masks import CONDITIONS
    from .simulation.engine import load_run_config

    run_dir = Path(args.run_dir)
    cfg = load_run_config(run_dir)
    snap = run_dir / "state.sqlite" if not args.snapshot else run_dir / "snapshots" / f"{args.snapshot}.sqlite"
    s = InterviewSession(cfg, snap, ledger_path=None, scope="inspect", mask=CONDITIONS[args.condition], reference_time=parse_iso(args.at) if args.at else None)
    try:
        if args.evidence:
            _print(evidence_tree(s.svc.store, args.evidence))
            return 0
        res = s.svc.retriever.retrieve(args.agent, args.query, s.now, kinds=s.mask.kinds, max_items=args.k, commit_access=False, purpose="inspect")
        print(f"query: {args.query!r}  agent: {args.agent}  at: {s.now}  mode: {res.mode}  weights: {res.weights.__dict__}")
        print(f"eligible: {len(res.candidates)}  delivered: {len(res.delivered)}  budget: {res.budget_tokens} tokens (used {res.used_tokens})\n")
        print(f"{'rank':>4} {'score':>6} {'rec':>5} {'imp':>5} {'rel':>5}  {'id':<24} text")
        for c in res.candidates[: args.k]:
            n = c.components(res.weights, res.mode)
            mark = "*" if c.delivered else " "
            print(
                f"{c.rank:>4}{mark}{c.score:>6.3f} {n['recency']:>5.2f} {n['importance']:>5.2f} {n['relevance']:>5.2f}  {c.memory.id:<24} {c.memory.description[:90]}"
            )
        if len(res.candidates) >= 2:
            ex = res.explain(res.candidates[0].memory.id, res.candidates[1].memory.id)
            print(f"\nwhy #1 outranked #2: {ex['verdict']}")
            print("component differences: " + ", ".join(f"{k} {v:+.3f}" for k, v in ex["difference"].items()))
        refl = [c for c in res.candidates[: args.k] if c.memory.kind.value == "reflection"]
        if refl:
            print(f"\nevidence tree of {refl[0].memory.id}:")
            _print_tree(evidence_tree(s.svc.store, refl[0].memory.id))
    finally:
        s.close()
    return 0


def _print_tree(node: dict[str, Any], indent: int = 0) -> None:
    print("  " * indent + f"- [{node.get('kind', '?')}] {node.get('id')}: {node.get('description', '')[:100]}")
    for child in node.get("evidence", []):
        _print_tree(child, indent + 1)


# ---------------------------------------------------------------------- evaluation
def cmd_interview(args: argparse.Namespace) -> int:
    from .db import parse_iso
    from .evaluation.interview import DEFAULT_CONDITIONS, InterviewSession, InterviewSpec, run_interviews
    from .memory.masks import CONDITIONS
    from .simulation.engine import load_run_config

    run_dir = Path(args.run_dir)
    cfg = load_run_config(run_dir)
    if args.protocol:
        import yaml

        from .config import repo_path

        proto = yaml.safe_load((Path(args.protocol) if Path(args.protocol).exists() else repo_path(args.protocol)).read_text()) or {}
        args.snapshot = args.snapshot or proto.get("snapshot")
        args.condition = args.condition or proto.get("conditions")
        args.bank = proto.get("bank", args.bank) if args.bank == DEFAULT_BANK else args.bank
        args.name = proto.get("name", args.name) if args.name == "interviews" else args.name
        args.seed = proto.get("seed", args.seed) if args.seed == 0 else args.seed
        args.reference_time = args.reference_time or proto.get("reference_time")
    snap = Path(args.snapshot) if args.snapshot and args.snapshot.endswith(".sqlite") else run_dir / "snapshots" / f"{args.snapshot or 'final'}.sqlite"
    ref = parse_iso(args.reference_time) if args.reference_time else None
    if args.ask:
        if not args.agent:
            print("--ask needs --agent")
            return 2
        for cond in args.condition or ["full_architecture"]:
            s = InterviewSession(
                cfg, snap, ledger_path=run_dir / "provider.sqlite", scope=f"{run_dir.name}::ask::{cond}", mask=CONDITIONS[cond], reference_time=ref
            )
            a = s.ask(args.agent[0], args.ask)
            print(f"[{cond}] {a.answer}\n  (retrieved {len(a.retrieved_ids)} memories: {a.retrieved_kinds})")
            s.close()
        return 0
    spec = InterviewSpec(
        run_dir=run_dir,
        snapshot=snap,
        conditions=args.condition or list(DEFAULT_CONDITIONS),
        bank=args.bank,
        agents=args.agent,
        questions=args.question,
        reference_time=ref,
        seed=args.seed,
        name=args.name,
    )
    out = run_interviews(spec, cfg)
    m = out["manifest"]
    print(
        f"{m['responses']} answers ({len(m['agents'])} agents × {len(m['questions'])} questions × {len(m['conditions'])} conditions) at {m['reference_time']} → {out['dir']}"
    )
    print("human condition: not generated. Import genuine crowdworker answers with: ga export-blinded --human-responses FILE")
    return 0


def cmd_export_blinded(args: argparse.Namespace) -> int:
    from .evaluation.export import blinded_export
    from .evaluation.human import import_human_responses
    from .evaluation.interview import read_jsonl
    from .evaluation.question_bank import QuestionBank
    from .scenario.loader import load_scenario
    from .simulation.engine import load_run_config

    run_dir = Path(args.run_dir)
    base = run_dir / "exports" / "interviews" / args.name
    rows = read_jsonl(base / "responses.jsonl")
    cfg = load_run_config(run_dir)
    from .config import repo_path

    sc = load_scenario(repo_path(cfg.scenario.path), population=cfg.scenario.population)
    if args.human_responses:
        manifest = json.loads((base / "manifest.json").read_text())
        bank = QuestionBank.load(manifest["bank"]["path"])
        qtext = {}
        for r in rows:
            qtext.setdefault(r["question_id"], r["question"])
        for q in bank.questions:
            qtext.setdefault(q.id, q.text)
        human = import_human_responses(args.human_responses, question_text=qtext, agent_names={a: sc.agents[a].identity.name for a in sc.agent_ids})
        rows += human
        print(f"imported {len(human)} genuine human responses from {args.human_responses}")
    info = blinded_export(rows, base / "blinded", seed=args.seed, run_info={"run_dir": str(run_dir), "snapshot": args.name}, identities=sc.identities())
    print(f"{info['items']} rating items ({info['answers']} answers) → {info['dir']}")
    print("give raters rating_form.csv, rating_items.csv, rubric.md and context/; keep blinding_key.json private")
    return 0


def cmd_analyze_ratings(args: argparse.Namespace) -> int:
    from .evaluation.export import load_key
    from .evaluation.human import import_rankings
    from .evaluation.stats import analyze

    base = Path(args.run_dir) / "exports" / "interviews" / args.name / "blinded"
    key = load_key(base / "blinding_key.json")
    rankings = import_rankings(args.ratings, key)
    conditions = sorted({c for item in key.values() for c in item["labels"].values()})
    res = analyze(rankings, conditions, source=f"human ratings from {args.ratings}")
    (base / "analysis.json").write_text(json.dumps(res, indent=2))
    _print(res)
    return 0


def cmd_judge(args: argparse.Namespace) -> int:
    from .evaluation.interview import read_jsonl, write_jsonl
    from .evaluation.judge import judge_responses
    from .scenario.loader import load_scenario
    from .simulation.engine import load_run_config

    run_dir = Path(args.run_dir)
    cfg = load_run_config(run_dir)
    base = run_dir / "exports" / "interviews" / args.name
    rows = read_jsonl(base / "responses.jsonl")
    from .config import repo_path

    sc = load_scenario(repo_path(cfg.scenario.path), population=cfg.scenario.population)
    res = judge_responses(rows, sc.identities(), cfg, ledger_path=run_dir / "provider.sqlite", scope=f"{run_dir.name}::judge::{args.name}")
    write_jsonl(base / "llm_judge_exploratory.jsonl", res["rows"])
    (base / "llm_judge_exploratory_summary.json").write_text(json.dumps(res["summary"], indent=2))
    print("EXPLORATORY LLM JUDGE (not human believability):")
    _print(res["summary"])
    return 0


def cmd_evaluate(args: argparse.Namespace) -> int:
    from .evaluation.evaluate import evaluate_run
    from .simulation.engine import load_run_config

    run_dir = Path(args.run_dir)
    cfg = load_run_config(run_dir)
    res = evaluate_run(run_dir, cfg, relationships=not args.no_relationships, min_minutes=args.min_minutes)
    for snap, s in res["snapshots"].items():
        for key, d in s["diffusion"].items():
            print(f"{snap:<8} {key:<18} claimed {d['claimed']}/{d['n']}, claimed and supported {d['supported_aware']}/{d['n']}")
        if s.get("relationships"):
            g = s["relationships"]
            print(f"{snap:<8} relationship density (mutual, supported) {g['density_supported']}")
    if res.get("attendance"):
        a = res["attendance"]["among_invited"]
        print(f"party: {a['attended']} of {a['n']} invited guests attended")
    for x in res["not_measured"]:
        print(f"not measured: {x}")
    print(f"report: {res['dir']}/report.md")
    return 0


def cmd_experiment(args: argparse.Namespace) -> int:
    from .evaluation.experiment import Protocol, estimate, execute

    proto = Protocol.load(args.protocol)
    est = estimate(proto, args.measured_run)
    print(f"protocol {proto.name}: {len(proto.runs())} independent runs ({', '.join(proto.conditions)}) × seeds {proto.seeds}")
    _print(est)
    if not args.execute:
        print("Planned only. Add --execute to run the batch (live protocols spend real API calls).")
        return 0
    local = proto.config_for(proto.runs()[0]).providers.llm.is_local()
    if est["mode"] == "live" and not args.yes and not local:
        print("This protocol is live. Add --yes as well to confirm.")
        return 2
    res = execute(proto, progress=lambda r: print(f"  {r['run_id']}: {r.get('status')} {r.get('stop_detail') or ''}", flush=True))
    print(f"report: {res['dir']}/report.md")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print("the viewer needs: pip install -e .[viewer]")
        return 1
    from .viewer.app import create_app

    app = create_app(Path(args.run_dir), experiment_dir=Path(args.experiment) if args.experiment else None)
    print(f"Smallville Lab viewer on http://{args.host}:{args.port}  (read-only; replays recorded frames, never calls a model)")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from .simulation.export import export_run

    out = export_run(Path(args.run_dir))
    for k, v in out.items():
        print(f"{k:<14} {v}")
    return 0


def cmd_prompt_examples(args: argparse.Namespace) -> int:
    from .prompt_examples import write_prompt_examples

    out = write_prompt_examples([Path(d) for d in args.run_dir], args.out)
    print(f"wrote {len(out['tasks'])} task files and README.md to {out['dir']}")
    if out["without_examples"]:
        print("no successful call recorded for: " + ", ".join(out["without_examples"]))
        print("  (interview, awareness and judge come from ga interview / ga evaluate / ga judge on the run;")
        print("   seed_thought and conversation_inferences only run with their compatibility settings)")
    return 0


def cmd_import_scenario(args: argparse.Namespace) -> int:
    from .scenario.importer import import_official

    audit = import_official(Path(args.source), Path(args.out))
    _print(audit)
    return 0


def cmd_audit_scenario(args: argparse.Namespace) -> int:
    from .config import repo_path
    from .scenario.audit import audit_scenario
    from .scenario.loader import load_scenario

    rep = audit_scenario(load_scenario(repo_path(args.scenario), candidacy_seed_policy=args.policy))
    _print({k: v for k, v in rep.items() if k != "per_agent"} if not args.full else rep)
    return 0 if rep["ok"] else 1


# ---------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ga", description="Generative Agents reproduction lab")
    sub = p.add_subparsers(dest="command", required=True)

    def with_config(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--config", help="YAML config (see configs/)")
        sp.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override a config value, e.g. --set scenario.end=2023-02-13T12:00:00")

    sp = sub.add_parser("doctor", help="validate config, sources, providers and environment")
    with_config(sp)
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("run", help="bounded headless simulation")
    with_config(sp)
    sp.add_argument("--run-dir")
    sp.add_argument("--run-id")
    sp.add_argument("--max-steps", type=int)
    sp.add_argument("--until", help="stop at this simulation time (ISO)")
    sp.add_argument("--interventions", help="YAML list of timed interventions")
    sp.add_argument("--yes", action="store_true", help="confirm a live run within its configured limits")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("resume", help="continue a stopped run from its last checkpoint")
    sp.add_argument("--run-dir", required=True)
    sp.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="e.g. raise a budget: --set budget.max_calls=20000")
    sp.add_argument("--max-steps", type=int)
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(func=cmd_resume)

    sp = sub.add_parser("replay", help="re-execute a run from its recorded ledger (no model calls) and compare")
    sp.add_argument("--run-dir", required=True)
    sp.add_argument("--out")
    sp.set_defaults(func=cmd_replay)

    sp = sub.add_parser("inspect-memory", help="retrieval trace with score components, ranking explanation and evidence trees")
    sp.add_argument("--run-dir", required=True)
    sp.add_argument("--agent", required=True)
    sp.add_argument("--query", default="")
    sp.add_argument("--k", type=int, default=12)
    sp.add_argument("--at", help="query time (default: the run's current time)")
    sp.add_argument("--snapshot", help="snapshot name instead of the live state")
    sp.add_argument("--condition", default="full_architecture", choices=["full_architecture", "no_reflection", "observations_only", "no_memory_stream"])
    sp.add_argument("--evidence", help="print the evidence tree of this memory id")
    sp.set_defaults(func=cmd_inspect_memory)

    sp = sub.add_parser("interview", help="matched-history interviews on a snapshot")
    sp.add_argument("--run-dir", required=True)
    sp.add_argument("--snapshot", help="snapshot name (default final) or a .sqlite path")
    sp.add_argument("--condition", action="append", choices=["full_architecture", "no_reflection", "observations_only", "no_memory_stream"])
    sp.add_argument("--protocol", help="interview protocol YAML (e.g. configs/interviews_reference.yaml)")
    sp.add_argument("--bank", default=DEFAULT_BANK)
    sp.add_argument("--agent", action="append")
    sp.add_argument("--question", action="append", help="question id (repeatable)")
    sp.add_argument("--reference-time", help="interview clock (default: the snapshot's time)")
    sp.add_argument("--seed", type=int, default=0, help="placeholder sampling seed")
    sp.add_argument("--name", default="interviews")
    sp.add_argument("--ask", help="ask one free-form question instead of the bank")
    sp.set_defaults(func=cmd_interview)

    sp = sub.add_parser("export-blinded", help="blinded rating export for human evaluators")
    sp.add_argument("--run-dir", required=True)
    sp.add_argument("--name", default="interviews")
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--human-responses", help="CSV of genuine crowdworker answers to include")
    sp.set_defaults(func=cmd_export_blinded)

    sp = sub.add_parser("analyze-ratings", help="TrueSkill / Kruskal–Wallis / Dunn / Holm (+ labeled Friedman) on human rankings")
    sp.add_argument("--run-dir", required=True)
    sp.add_argument("--name", default="interviews")
    sp.add_argument("--ratings", required=True)
    sp.set_defaults(func=cmd_analyze_ratings)

    sp = sub.add_parser("judge", help="EXPLORATORY LLM judge over interview answers")
    sp.add_argument("--run-dir", required=True)
    sp.add_argument("--name", default="interviews")
    sp.set_defaults(func=cmd_judge)

    sp = sub.add_parser("evaluate", help="end-to-end measurements (diffusion, relationships, attendance, failures)")
    sp.add_argument("--run-dir", required=True)
    sp.add_argument("--no-relationships", action="store_true")
    sp.add_argument("--min-minutes", type=float, default=10.0)
    sp.set_defaults(func=cmd_evaluate)

    sp = sub.add_parser("experiment", help="bounded independent runs (plans and estimates unless --execute)")
    sp.add_argument("--protocol", required=True)
    sp.add_argument("--measured-run", help="a pilot run directory to project usage from")
    sp.add_argument("--execute", action="store_true")
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(func=cmd_experiment)

    sp = sub.add_parser("serve", help="local read-only viewer and inspector")
    sp.add_argument("--run-dir", required=True)
    sp.add_argument("--experiment", help="experiment directory to show in the Experiment tab")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8000)
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser("export", help="JSONL/CSV/Markdown exports of a run")
    sp.add_argument("--run-dir", required=True)
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("prompt-examples", help="per-task input/output examples from recorded call ledgers")
    sp.add_argument("--run-dir", required=True, nargs="+", help="one or more runs; each task's example comes from the first run that has one")
    sp.add_argument("--out", default=None, help="default: RUN_DIR/exports/prompt_examples")
    sp.set_defaults(func=cmd_prompt_examples)

    sp = sub.add_parser("import-scenario", help="convert the official Smallville data into scenario files")
    sp.add_argument("--source", required=True, help="path to a joonspk-research/generative_agents checkout")
    sp.add_argument("--out", default="scenarios")
    sp.set_defaults(func=cmd_import_scenario)

    sp = sub.add_parser("audit-scenario", help="check seeds, knowledge scoping, spawn tiles and places")
    sp.add_argument("--scenario", default="scenarios/smallville_n25/scenario.yaml")
    sp.add_argument("--policy", default="paper_originator_only", choices=["paper_originator_only", "released_csv"])
    sp.add_argument("--full", action="store_true")
    sp.set_defaults(func=cmd_audit_scenario)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
