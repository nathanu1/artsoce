"""``ga evaluate``: the end-to-end measurements of §7 for one run, with an auditable report.

Probes (awareness and "Do you know of <name>?") run on clones of the run's snapshots
("initial" right after seeding, "final" when the run completed). Transmissions, attendance
and failure examples come from the run's own records. Outputs go to
``<run>/exports/evaluation/``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import GAConfig
from ..db import Database, parse_iso
from ..memory.masks import FULL
from ..scenario.loader import load_scenario
from ..world.constraints import Constraints
from . import attendance as att
from . import diffusion as dif
from . import failures as fail
from . import relationships as rel
from .evidence import load_topics
from .interview import InterviewSession, write_csv, write_jsonl
from .plots import bar_chart, network

PAPER_REFERENCE = [
    ("Mayoral candidacy awareness", "1/25 initially, 8/25 finally"),
    ("Party awareness", "1/25 initially, 13/25 finally (incl. Isabella)"),
    ("Party guest attendance", "5 of 12 invited agents"),
    ("Relationship network density", "0.167 initially, 0.74 finally"),
    ("Hallucinated relationship answers", "6 of 453 responses (about 1.3%)"),
]


def evaluate_run(
    run_dir: str | Path,
    cfg: GAConfig,
    *,
    snapshots: tuple[str, ...] = ("initial", "final"),
    relationships: bool = True,
    min_minutes: float = 10.0,
    provider: Any = None,
    embedding_provider: Any = None,
    out_name: str = "evaluation",
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    state = Database(run_dir / "state.sqlite", read_only=True)
    run_id = state.get_meta("run_id") or run_dir.name
    mode = state.get_meta("mode") or cfg.run_mode
    snaps = state.get_meta("snapshots", {}) or {}
    status = state.get_meta("status")
    scenario = load_scenario(
        cfg.scenario.path if Path(cfg.scenario.path).is_absolute() else _repo(cfg.scenario.path),
        population=cfg.scenario.population,
        candidacy_seed_policy=cfg.scenario.candidacy_seed_policy,
    )
    topics = load_topics(scenario.events)
    agents = list(scenario.agent_ids)
    names = {a: scenario.agents[a].identity.name for a in agents}
    out_dir = run_dir / "exports" / out_name
    out_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {"run_id": run_id, "mode": mode, "run_status": status, "agents": agents, "snapshots": {}, "not_measured": []}

    diffusion_rows: list[dict[str, Any]] = []
    relationship_rows: list[dict[str, Any]] = []
    for snap in snapshots:
        info = snaps.get(snap)
        if not info:
            result["not_measured"].append(f"snapshot '{snap}' does not exist (run status: {status})")
            continue
        path = run_dir / info["path"]
        session = InterviewSession(
            cfg,
            path,
            ledger_path=run_dir / "provider.sqlite",
            scope=f"{run_id}::probe::{snap}",
            mask=FULL,
            provider=provider,
            embedding_provider=embedding_provider,
        )
        try:
            snap_res: dict[str, Any] = {"sim_time": info["sim_time"], "diffusion": {}, "relationships": None}
            for key, topic in topics.items():
                if not topic.probe_question:
                    continue
                rows = dif.probe_awareness(session, topic, agents)
                for r in rows:
                    r["snapshot"] = snap
                diffusion_rows += rows
                snap_res["diffusion"][key] = dif.summarize(rows)
            if relationships:
                rows = rel.probe_relationships(session, agents)
                for r in rows:
                    r["snapshot"] = snap
                relationship_rows += rows
                g = rel.graph(rows, agents)
                snap_res["relationships"] = g
            result["snapshots"][snap] = snap_res
        finally:
            session.close()

    trans = {key: dif.transmissions(state, t) for key, t in topics.items()}
    result["transmissions"] = {k: {"count": len(v), "receivers": len(dif.first_exposures(v))} for k, v in trans.items()}
    attendance_report = None
    party = next((t for t in topics.values() if t.window and t.place), None)
    if party is not None:
        reached = parse_iso(state.get_meta("sim_time"))
        if reached is None or reached < party.window[1]:
            result["not_measured"].append(f"attendance: the run stopped at {reached} before the {party.key} window ended ({party.window[1]})")
        else:
            attendance_report = att.attendance(
                state, scenario.world, party, agents, host=party.originator, seconds_per_step=cfg.scenario.seconds_per_step, min_minutes=min_minutes
            )
            result["attendance"] = attendance_report["summary"]
    reference = Constraints.load(scenario.constraints_path, "strict-v1")
    final_diff = [r for r in diffusion_rows if r["snapshot"] == snapshots[-1]]
    final_rel = [r for r in relationship_rows if r["snapshot"] == snapshots[-1]]
    failures = fail.taxonomy(
        state,
        diffusion_rows=final_diff,
        relationship_rows=final_rel,
        attendance_report=attendance_report,
        world=scenario.world,
        reference_constraints=reference,
        identities=scenario.identities(),
    )
    result["failures"] = {k: v["count"] for k, v in failures.items()}

    write_jsonl(out_dir / "diffusion.jsonl", diffusion_rows)
    write_csv(
        out_dir / "diffusion.csv",
        diffusion_rows,
        [
            "snapshot",
            "event",
            "agent_id",
            "originator",
            "claims_knowledge",
            "supported",
            "status",
            "claimed_details",
            "evidence_details",
            "unsupported_details",
            "first_exposure",
            "first_source",
            "answer",
        ],
    )
    all_trans = [t for v in trans.values() for t in v]
    write_csv(out_dir / "transmissions.csv", all_trans, ["event", "time", "conversation_id", "turn", "sender", "receiver", "details", "invitation", "text"])
    write_jsonl(out_dir / "relationships.jsonl", relationship_rows)
    write_csv(out_dir / "relationships.csv", relationship_rows, ["snapshot", "asker", "about", "claims_knowledge", "status", "evidence_kinds", "answer"])
    if attendance_report:
        write_csv(
            out_dir / "attendance.csv",
            attendance_report["rows"],
            ["agent_id", "host", "exposed", "first_exposure", "invited", "accepted", "scheduled", "present_minutes", "attended", "other_plans_in_window"],
        )
    (out_dir / "failures.json").write_text(json.dumps(failures, indent=2, default=str))
    (out_dir / "summary.json").write_text(json.dumps(result, indent=2, default=str))
    _plots(out_dir, result, trans, names, topics)
    (out_dir / "report.md").write_text(render_report(result, failures, attendance_report, names))
    state.close()
    result["dir"] = str(out_dir)
    return result


def _repo(rel: str) -> Path:
    from ..config import repo_path

    return repo_path(rel)


def _plots(out_dir: Path, result: dict[str, Any], trans: dict[str, list[dict[str, Any]]], names: dict[str, str], topics: dict[str, Any]) -> None:
    snaps = list(result["snapshots"])
    for key in topics:
        if not any(key in result["snapshots"][s]["diffusion"] for s in snaps):
            continue
        claimed = [result["snapshots"][s]["diffusion"].get(key, {}).get("claimed") for s in snaps]
        supported = [result["snapshots"][s]["diffusion"].get(key, {}).get("supported_aware") for s in snaps]
        (out_dir / f"diffusion_{key}.svg").write_text(bar_chart(f"{key}: agents aware", snaps, {"claimed": claimed, "claimed and supported": supported}))
        first = dif.first_exposures(trans.get(key, []))
        edges = [(names.get(t["sender"], t["sender"]).split()[0], names.get(r, r).split()[0]) for r, t in first.items()]
        (out_dir / f"diffusion_path_{key}.svg").write_text(
            network(
                f"{key}: first transmissions",
                [n.split()[0] for n in names.values()],
                edges,
                directed=True,
                highlight=names[topics[key].originator].split()[0] if topics[key].originator in names else None,
            )
        )
    if "final" in result["snapshots"] and result["snapshots"]["final"].get("relationships"):
        g = result["snapshots"]["final"]["relationships"]
        edges = [(names[a].split()[0], names[b].split()[0]) for a, b in g["edges_supported"]]
        (out_dir / "relationships_final.svg").write_text(
            network(f"supported relationships, density {g['density_supported']}", [n.split()[0] for n in names.values()], edges)
        )


def _pct(k: int | None, n: int | None) -> str:
    if k is None or not n:
        return "n/a"
    return f"{k}/{n} ({100 * k / n:.0f}%)"


def render_report(result: dict[str, Any], failures: dict[str, Any], attendance_report: dict[str, Any] | None, names: dict[str, str]) -> str:
    mode = str(result["mode"]).upper()
    lines = [f"# End-to-end evaluation: {result['run_id']}", ""]
    if mode in ("MOCK", "REPLAY"):
        lines += [
            f"> **{mode} RUN.** Outcomes come from the offline mock model and hash embeddings (or a replay of them). "
            "They demonstrate that the measurement pipeline works; they are not evidence about generative agents or the paper.",
            "",
        ]
    lines += [f"Run status: `{result['run_status']}` · agents: {len(result['agents'])} · mode: {mode}", ""]
    if result["not_measured"]:
        lines += ["**Not measured:**", ""] + [f"* {x}" for x in result["not_measured"]] + [""]
    lines += [
        "## Information diffusion",
        "",
        "| Snapshot | Event | Claimed | Claimed and supported by memory | Newly informed (supported) | Claimed without support | Evidence but denied |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for snap, s in result["snapshots"].items():
        for key, d in s["diffusion"].items():
            lines.append(
                f"| {snap} ({s['sim_time']}) | {key} | {_pct(d['claimed'], d['n'])} | {_pct(d['supported_aware'], d['n'])} | {d['newly_informed_supported']} | {d['claimed_unsupported']} | {d['retrieval_failures']} |"
            )
    lines += [
        "",
        "Percentages include the originator. Transmissions found in transcripts: "
        + ", ".join(f"{k}: {v['count']} statements reaching {v['receivers']} agents" for k, v in result["transmissions"].items()),
        "",
    ]
    lines += [
        "## Relationships",
        "",
        "| Snapshot | Density (mutual, memory-supported) | Density (mutual claims, unvalidated) | Affirmative answers | Without any evidence | Seen only |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for snap, s in result["snapshots"].items():
        g = s.get("relationships")
        if g:
            lines.append(
                f"| {snap} | {g['density_supported']} | {g['density_claimed']} | {g['affirmative']}/{g['responses']} | {g['hallucinated']} ({g['hallucinated_pct']}%) | {g['observed_only']} |"
            )
    lines += [""]
    if attendance_report:
        s = attendance_report["summary"]
        lines += [
            "## Coordination (physical attendance)",
            "",
            f"Place `{attendance_report['place']}`, window {attendance_report['window'][0]} – {attendance_report['window'][1]}, present at least {attendance_report['min_minutes']} minutes. Host excluded from guest denominators.",
            "",
            "| Group | Attended |",
            "| --- | --- |",
            f"| Invited guests | {_pct(s['among_invited']['attended'], s['among_invited']['n'])} |",
            f"| Exposed guests | {_pct(s['among_exposed']['attended'], s['among_exposed']['n'])} |",
            f"| Accepted (said yes) | {_pct(s['among_accepted']['attended'], s['among_accepted']['n'])} |",
            f"| Scheduled it | {_pct(s['among_scheduled']['attended'], s['among_scheduled']['n'])} |",
            f"| Present without an invitation | {s['uninvited_present']} |",
            "",
        ]
    lines += ["## Failures", "", "| Category | Count | Rule |", "| --- | --- | --- |"]
    for cat, v in failures.items():
        lines.append(f"| {cat} | {v['count']} | {v['rule']} |")
    lines += ["", "Examples are in `failures.json`.", "", "## Paper reference (comparison only, not a target)", "", "| Outcome | Paper (§7) |", "| --- | --- |"]
    lines += [f"| {a} | {b} |" for a, b in PAPER_REFERENCE]
    lines += [
        "",
        "These are simulated characters. Behavior that looks plausible in this town does not establish validity for real human populations.",
        "",
    ]
    return "\n".join(lines)
