"""Matched-history interviews on frozen snapshots (paper §6; spec M-1 … M-5, N-5).

A snapshot is a committed copy of a run's state. Every condition gets its own in-memory
clone of it, so nothing an interview does (retrieval traces, summary caches) can reach the
run, another condition or the next question:

* memory masks are applied before retrieval and before the dynamic summary is built, and
  every answer is checked to have used only permitted memory kinds;
* retrieval never updates access times (``commit_access=False``), so questions are
  answered independently;
* the dynamic summary is rebuilt at the reference time from the condition's permitted
  memories (cached per condition within the session only);
* the static identity block is the same in every condition;
* "today" resolves against the explicit reference time (default: the snapshot's time).

Interview calls are recorded in the run's provider ledger under their own scope, so
re-running the same interview is a replay, not a new sample.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..cognition.context import bullet, identity_block
from ..cognition.summary import SummaryService
from ..config import GAConfig
from ..db import Database, parse_iso
from ..memory.masks import CONDITIONS, FULL, MemoryMask
from ..memory.store import MemoryStore
from ..schemas import AgentIdentity
from ..simulation.clock import long_time
from ..simulation.runtime import build_runtime, make_services
from .question_bank import QuestionBank, select_placeholders

DEFAULT_CONDITIONS = ["full_architecture", "no_reflection", "observations_only", "no_memory_stream"]


def open_snapshot(path: str | Path) -> Database:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"snapshot not found: {p}")
    return Database(p, read_only=True)


def snapshot_info(db: Database) -> dict[str, Any]:
    info = db.get_meta("snapshot") or {}
    return {
        "name": info.get("name", "state"),
        "run_id": info.get("run_id") or db.get_meta("run_id"),
        "step": info.get("step", db.get_meta("next_step")),
        "sim_time": info.get("sim_time") or db.get_meta("sim_time"),
    }


@dataclass
class Answer:
    agent_id: str
    condition: str
    question: str
    answer: str
    retrieved_ids: list[str] = field(default_factory=list)
    retrieved_kinds: dict[str, int] = field(default_factory=dict)
    call_ids: list[int] = field(default_factory=list)
    reference_time: str = ""


class InterviewSession:
    """Answers questions as agents of one snapshot under one memory condition."""

    def __init__(
        self,
        cfg: GAConfig,
        snapshot: str | Path,
        *,
        ledger_path: str | Path | None,
        scope: str,
        mask: MemoryMask = FULL,
        reference_time: datetime | None = None,
        provider: Any = None,
        embedding_provider: Any = None,
        interviewer: str = "an interviewer",
    ):
        self.cfg = cfg
        self.mask = mask
        self.interviewer = interviewer
        src = open_snapshot(snapshot)
        self.source_info = snapshot_info(src)
        self.db = src.clone()  # private, in memory
        src.close()
        self.now = reference_time or parse_iso(self.source_info["sim_time"])
        if self.now is None:
            raise ValueError("snapshot has no simulation time; pass reference_time")
        store = MemoryStore(self.db)
        self.rt = build_runtime(
            cfg, store=store, ledger_path=ledger_path, scope=scope, provider=provider, embedding_provider=embedding_provider, step_getter=lambda: -2
        )
        self.rt.budget.max_calls = None  # interviews are bounded by their question count
        self.identities = {
            r["id"]: AgentIdentity.model_validate_json(r["identity_json"]) for r in self.db.query("SELECT id, identity_json FROM agents ORDER BY order_index")
        }
        self.svc = make_services(cfg, self.db, self.rt, self.identities)
        self.summaries = SummaryService(self.svc)
        self._summary_cache: dict[str, str] = {}

    def close(self) -> None:
        self.db.close()
        self.rt.ledger.close()

    def description(self, agent_id: str) -> str:
        if agent_id not in self._summary_cache:
            ident = self.identities[agent_id]
            dyn = self.summaries.dynamic(ident, self.now, mask=self.mask, force=True, commit_access=False)
            self._summary_cache[agent_id] = "\n".join(p for p in (identity_block(ident, self.now), dyn) if p)
        return self._summary_cache[agent_id]

    def ask(self, agent_id: str, question: str) -> Answer:
        ident = self.identities[agent_id]
        mems = []
        if not self.mask.empty:
            res = self.svc.retriever.retrieve(
                agent_id,
                question,
                self.now,
                kinds=self.mask.kinds,
                max_items=self.cfg.interview.retrieval_items,
                commit_access=False,
                purpose=f"interview:{self.mask.name}",
            )
            mems = res.delivered
        kinds = Counter(m.kind.value for m in mems)
        leaked = [m.id for m in mems if not self.mask.allows(m)]
        if leaked:  # pragma: no cover - guarded by retrieval filtering
            raise AssertionError(f"mask {self.mask.name} leaked {leaked}")
        out = self.svc.gateway.run(
            "interview",
            {
                "agent_summary": self.description(agent_id),
                "now": long_time(self.now),
                "agent_name": ident.name,
                "statements": bullet(mems) if mems else "(no memories available)",
                "interviewer": self.interviewer,
                "question": question,
                "_question": question,
                "_statements": [m.description for m in mems],
            },
            agent_id=agent_id,
            sim_time=self.now,
            purpose=f"interview:{self.mask.name}",
        )
        return Answer(agent_id, self.mask.name, question, out.output.answer.strip(), [m.id for m in mems], dict(kinds), out.call_ids, self.now.isoformat())


@dataclass
class InterviewSpec:
    run_dir: Path
    snapshot: Path
    conditions: list[str] = field(default_factory=lambda: list(DEFAULT_CONDITIONS))
    bank: str = "configs/questions/appendix_b_reference.yaml"
    agents: list[str] | None = None
    questions: list[str] | None = None
    reference_time: datetime | None = None
    seed: int = 0
    name: str = "interviews"
    interviewer: str = "an interviewer"


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_interviews(spec: InterviewSpec, cfg: GAConfig, *, provider: Any = None, embedding_provider: Any = None) -> dict[str, Any]:
    """Interview every selected agent with every question under every condition."""

    unknown = [c for c in spec.conditions if c not in CONDITIONS]
    if unknown:
        raise ValueError(f"unknown conditions {unknown}; human answers are imported, never generated")
    bank = QuestionBank.load(spec.bank)
    before = _file_sha(spec.snapshot)
    src = open_snapshot(spec.snapshot)
    info = snapshot_info(src)
    names = {r["id"]: r["name"] for r in src.query("SELECT id, name FROM agents ORDER BY order_index")}
    agents = spec.agents or list(names)
    selections = {}
    for aid in agents:
        seeds = [r["description"] for r in src.query("SELECT description FROM memories WHERE owner_id=? AND seed=1", (aid,))]
        selections[aid] = select_placeholders(src, aid, names, seeds, seed=spec.seed)
    src.close()
    questions = [q for q in bank.questions if spec.questions is None or q.id in spec.questions]
    rows: list[dict[str, Any]] = []
    run_id = info["run_id"] or spec.run_dir.name
    for cond in spec.conditions:
        session = InterviewSession(
            cfg,
            spec.snapshot,
            ledger_path=spec.run_dir / "provider.sqlite",
            scope=f"{run_id}::interview::{spec.name}::{cond}",
            mask=CONDITIONS[cond],
            reference_time=spec.reference_time,
            provider=provider,
            embedding_provider=embedding_provider,
            interviewer=spec.interviewer,
        )
        try:
            for aid in agents:
                sel = selections[aid]
                for q in questions:
                    text = q.render(sel.bindings)
                    a = session.ask(aid, text)
                    rows.append(
                        {
                            "interview": spec.name,
                            "run_id": run_id,
                            "snapshot": info["name"],
                            "reference_time": a.reference_time,
                            "agent_id": aid,
                            "agent_name": names[aid],
                            "condition": cond,
                            "question_id": q.id,
                            "category": q.category,
                            "question": text,
                            "answer": a.answer,
                            "retrieved_ids": a.retrieved_ids,
                            "retrieved_kinds": a.retrieved_kinds,
                            "call_ids": a.call_ids,
                            "source": "generated",
                            "mode": cfg.run_mode,
                        }
                    )
        finally:
            session.close()
    after = _file_sha(spec.snapshot)
    if before != after:  # pragma: no cover - the snapshot is opened read-only
        raise RuntimeError("the snapshot changed during interviews")
    out_dir = spec.run_dir / "exports" / "interviews" / spec.name
    out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / "responses.jsonl", rows)
    write_csv(
        out_dir / "responses.csv",
        rows,
        ["agent_id", "agent_name", "condition", "question_id", "category", "question", "answer", "reference_time", "source", "mode"],
    )
    manifest = {
        "name": spec.name,
        "run_id": run_id,
        "snapshot": {"path": str(spec.snapshot), "sha256": before, **info},
        "reference_time": rows[0]["reference_time"] if rows else None,
        "bank": {"name": bank.name, "version": bank.version, "path": bank.path},
        "conditions": spec.conditions,
        "agents": agents,
        "questions": [q.id for q in questions],
        "placeholder_seed": spec.seed,
        "selections": {aid: {"bindings": s.bindings, "record": s.record} for aid, s in selections.items()},
        "mode": cfg.run_mode,
        "responses": len(rows),
        "human_condition": "not generated; import genuine responses with `ga interview import-human`",
        "side_effects": {"snapshot_sha256_before": before, "snapshot_sha256_after": after},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return {"rows": rows, "manifest": manifest, "dir": out_dir}


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in r.items() if k in columns})
