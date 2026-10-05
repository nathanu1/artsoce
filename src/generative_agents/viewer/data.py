"""Read-only access to a run for the viewer. Nothing here writes to the run or calls a model."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from functools import cached_property
from pathlib import Path
from typing import Any

from ..config import repo_path
from ..db import Database, parse_iso
from ..memory.evidence import evidence_tree
from ..memory.store import MemoryStore
from ..schemas import AgentIdentity
from ..simulation.engine import load_run_config
from ..world.hierarchy import WorldMap

# Agent colors from the design (darker, high-contrast hues for initials on light ground).
FIXED = {
    "isabella_rodriguez": "#A63D2A",
    "wolfgang_schulz": "#5E3F8F",
    "klaus_mueller": "#1E6E62",
    "maria_lopez": "#2D5FA8",
    "sam_moore": "#6E5A1E",
}
PALETTE = ["#8A3B62", "#2F6B3A", "#7A4A1F", "#3E5C8A", "#6A2F2F", "#2E6670", "#5B5B1E", "#4B3B8A", "#7D3F7A", "#2B5E4B", "#8A5A2B", "#40507A"]


class RunData:
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.db = Database(self.run_dir / "state.sqlite", read_only=True)
        self.lock = threading.Lock()
        self.cfg = load_run_config(self.run_dir)
        self.store = MemoryStore(self.db)

    def q(self, sql: str, params: tuple = ()) -> list[Any]:
        with self.lock:
            return self.db.query(sql, params)

    def one(self, sql: str, params: tuple = ()) -> Any:
        with self.lock:
            return self.db.one(sql, params)

    def meta(self, key: str, default: Any = None) -> Any:
        with self.lock:
            return self.db.get_meta(key, default)

    # ------------------------------------------------------------------ run and map
    @cached_property
    def world(self) -> WorldMap:
        scen = self.meta("scenario") or {}
        from ..scenario.loader import load_scenario

        sc = load_scenario(
            repo_path(self.cfg.scenario.path), population=self.cfg.scenario.population, candidacy_seed_policy=self.cfg.scenario.candidacy_seed_policy
        )
        if scen.get("map_sha256") and sc.manifest().get("map_sha256") != scen["map_sha256"]:
            raise RuntimeError("the map file changed since this run was recorded")
        return sc.world

    def agents(self) -> list[dict[str, Any]]:
        out = []
        for i, r in enumerate(self.q("SELECT id, name, order_index, identity_json FROM agents ORDER BY order_index")):
            ident = AgentIdentity.model_validate_json(r["identity_json"])
            st = self.one("SELECT json FROM agent_state WHERE agent_id=?", (r["id"],))
            perception = (json.loads(st["json"]).get("extra", {}) or {}).get("perception", {}) if st else {}
            out.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "initials": "".join(p[0] for p in r["name"].split()[:2]).upper(),
                    "color": FIXED.get(r["id"], PALETTE[i % len(PALETTE)]),
                    "vision_r": perception.get("vision_r", 8),
                    "identity": ident.model_dump(),
                }
            )
        return out

    def evaluator_events(self) -> list[dict[str, Any]]:
        """Ground truth for the researcher's overlay only (never sent to agents)."""

        from ..scenario.loader import load_scenario

        sc = load_scenario(repo_path(self.cfg.scenario.path), population=self.cfg.scenario.population)
        out = []
        for key, ev in sc.events.items():
            if ev.get("place"):
                w = ev.get("window") or {}
                out.append(
                    {
                        "key": key,
                        "label": ev.get("label", key),
                        "place": ev["place"],
                        "window": [str(w.get("start", ""))[11:16], str(w.get("end", ""))[11:16]] if w else None,
                    }
                )
        return out

    def run_info(self) -> dict[str, Any]:
        manifest = {}
        if (self.run_dir / "manifest.json").exists():
            manifest = json.loads((self.run_dir / "manifest.json").read_text())
        cfg = self.cfg
        last = self.one("SELECT MAX(step) AS s FROM frames")
        first = self.one("SELECT MIN(step) AS s FROM frames")
        return {
            "run_id": self.meta("run_id") or self.run_dir.name,
            "mode": self.meta("mode") or cfg.run_mode,
            "replay_of": manifest.get("replay_of"),
            "mock_llm": cfg.providers.llm.kind == "mock",
            "mock_embeddings": cfg.providers.embeddings.kind == "mock-hash",
            "status": self.meta("status"),
            "stop_detail": self.meta("stop_detail"),
            "next_step": self.meta("next_step", 0),
            "sim_time": self.meta("sim_time"),
            "start": cfg.scenario.start.isoformat(),
            "end": cfg.scenario.end.isoformat(),
            "seconds_per_step": cfg.scenario.seconds_per_step,
            "first_frame": first["s"] if first else None,
            "last_frame": last["s"] if last else None,
            "scenario": (self.meta("scenario") or {}).get("name"),
            "population": len(self.agents()),
            "settings": {
                "retrieval": f"{cfg.retrieval.mode} · weights {cfg.retrieval.weights.recency:g}/{cfg.retrieval.weights.importance:g}/{cfg.retrieval.weights.relevance:g} · {cfg.retrieval.decay_per_hour} per h",
                "reflection": f"{'on' if cfg.architecture.reflection else 'OFF'} · {cfg.reflection.mode} · > {cfg.reflection.threshold:g}",
                "constraints": cfg.constraints.policy,
                "tick": f"{cfg.scenario.seconds_per_step} s",
                "model": f"{cfg.providers.llm.kind}:{cfg.providers.llm.model}",
                "embeddings": f"{cfg.providers.embeddings.kind}:{cfg.providers.embeddings.model}",
            },
            "usage": (manifest.get("ledger") or {}),
            "limits": (manifest.get("budget") or {}).get("limits"),
            "snapshots": self.meta("snapshots", {}),
            "agents": self.agents(),
            "run_dir": str(self.run_dir),
            "evaluator_events": self.evaluator_events(),
        }

    def map_payload(self) -> dict[str, Any]:
        data = json.loads(Path(self.world_path()).read_text())
        w = self.world
        sectors = [{"address": a, "name": a.split(":")[-1], **box} for a, box in sorted(w.sector_boxes.items())]
        arenas = []
        for addr, tiles in w.address_tiles.items():
            if addr.count(":") != 2:
                continue
            xs = [t[0] for t in tiles]
            ys = [t[1] for t in tiles]
            arenas.append({"address": addr, "name": addr.split(":")[-1], "x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)})
        return {
            "world": w.world,
            "width": w.width,
            "height": w.height,
            "collision": data["layers"]["collision"],
            "sector_layer": data["layers"]["sector"],
            "sector_names": data["legend"]["sector"],
            "sectors": sectors,
            "arenas": arenas,
        }

    def world_path(self) -> Path:
        from ..scenario.loader import load_scenario

        sc = load_scenario(repo_path(self.cfg.scenario.path), population=self.cfg.scenario.population)
        return sc.map_path

    # ------------------------------------------------------------------ frames and timeline
    def time_at(self, step: int) -> datetime:
        return self.cfg.scenario.start + timedelta(seconds=step * self.cfg.scenario.seconds_per_step)

    def frames(self, start: int, end: int) -> dict[str, Any]:
        """Keyframe at or before ``start`` plus every delta up to ``end``."""

        key = self.one("SELECT MAX(step) AS s FROM frames WHERE step <= ? AND json LIKE '{\"key\":true%'", (start,))
        base = key["s"] if key and key["s"] is not None else -1
        rows = self.q("SELECT step, sim_time, json FROM frames WHERE step >= ? AND step <= ? ORDER BY step", (base, end))
        return {"from": base, "to": end, "frames": [{"step": r["step"], "t": r["sim_time"], **json.loads(r["json"])} for r in rows]}

    def timeline(self, day: str | None = None) -> dict[str, Any]:
        days = [r["day"] for r in self.q("SELECT DISTINCT day FROM plans WHERE level='hour' ORDER BY day")]
        day = day or (days[-1] if days else None)
        lanes = {}
        for a in self.agents():
            aid = a["id"]
            blocks = [
                json.loads(r["json"])
                for r in self.q("SELECT json FROM plans WHERE agent_id=? AND day=? AND level='hour' AND status != 'superseded' ORDER BY start", (aid, day))
            ]
            executed = []
            for e in self.q("SELECT sim_time, json FROM events WHERE type='action' AND agent_id=? AND substr(sim_time,1,10)=? ORDER BY id", (aid, day)):
                d = json.loads(e["json"])
                executed.append({"t": e["sim_time"], "activity": d.get("activity"), "address": d.get("address")})
            marks = []
            for e in self.q(
                "SELECT sim_time, type, json FROM events WHERE agent_id=? AND type IN ('replan','reflection','conversation','constraint','action_failure','intervention') AND substr(sim_time,1,10)=? ORDER BY id",
                (aid, day),
            ):
                d = json.loads(e["json"])
                label = {
                    "replan": d.get("inserted"),
                    "reflection": f"{d.get('stored', 0)} insights",
                    "conversation": d.get("summary"),
                    "constraint": d.get("message"),
                    "action_failure": d.get("reason"),
                    "intervention": d.get("kind"),
                }.get(e["type"])
                marks.append({"t": e["sim_time"], "type": e["type"], "label": label})
            convs = [
                json.loads(r["json"])
                for r in self.q("SELECT json FROM conversations WHERE participants LIKE ? AND substr(started_at,1,10)=? ORDER BY started_at", (f"%{aid}%", day))
            ]
            for c in convs:
                if aid != c["initiator_id"]:
                    marks.append({"t": c["started_at"], "type": "conversation", "label": c.get("summary")})
            lanes[aid] = {
                "blocks": [{"start": b["start"], "minutes": b["duration_min"], "activity": b["description"]} for b in blocks],
                "executed": executed,
                "marks": marks,
            }
        return {"days": days, "day": day, "lanes": lanes}

    # ------------------------------------------------------------------ agent inspector
    def agent(self, aid: str, step: int | None) -> dict[str, Any]:
        row = self.one("SELECT identity_json FROM agents WHERE id=?", (aid,))
        if row is None:
            raise KeyError(aid)
        ident = json.loads(row["identity_json"])
        st = self.one("SELECT json FROM agent_state WHERE agent_id=?", (aid,))
        state = json.loads(st["json"]) if st else {}
        t = self.time_at(step) if step is not None else parse_iso(self.meta("sim_time"))
        day = t.date().isoformat() if t else None
        plans = [json.loads(r["json"]) for r in self.q("SELECT json FROM plans WHERE agent_id=? AND day=? ORDER BY start, id", (aid, day))]
        hours = [p for p in plans if p["level"] == "hour" and p["status"] != "superseded"]
        tasks = [p for p in plans if p["level"] == "task"]
        for h in hours:
            h["tasks"] = [x for x in tasks if x.get("parent_id") == h["id"]]
        day_plan = next((p for p in plans if p["level"] == "day"), None)
        spatial = self.one("SELECT json FROM spatial_memory WHERE agent_id=?", (aid,))
        sm = json.loads(spatial["json"]) if spatial else {"tree": {}}
        known = [{"sector": s, "arenas": sorted(arenas)} for w, secs in sm.get("tree", {}).items() for s, arenas in sorted(secs.items())]
        counts = {r["kind"]: r["n"] for r in self.q("SELECT kind, COUNT(*) AS n FROM memories WHERE owner_id=? GROUP BY kind", (aid,))}
        latest_trace = self.one(
            "SELECT id FROM retrieval_traces WHERE agent_id=? AND sim_time <= ? ORDER BY sim_time DESC, id DESC LIMIT 1", (aid, (t or datetime.max).isoformat())
        )
        return {
            "identity": ident,
            "state": {
                "tile": state.get("tile"),
                "action": state.get("action"),
                "reflection_accumulator": state.get("reflection_accumulator"),
                "reflection_threshold": self.cfg.reflection.threshold,
                "reflections_done": state.get("reflections_done"),
                "last_reflection_at": state.get("last_reflection_at"),
                "failures": state.get("failures"),
                "note": "state as of the last committed checkpoint",
            },
            "day": day,
            "day_plan": day_plan,
            "hours": hours,
            "memory_counts": counts,
            "known_places": known,
            "latest_trace": latest_trace["id"] if latest_trace else None,
        }

    def memories(self, aid: str, *, kind: str | None, text: str | None, limit: int, before: str | None) -> list[dict[str, Any]]:
        sql = "SELECT id, kind, origin, description, created_at, last_accessed_at, importance, depth, evidence_json, conversation_id FROM memories WHERE owner_id=?"
        params: list[Any] = [aid]
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        if text:
            sql += " AND description LIKE ?"
            params.append(f"%{text}%")
        if before:
            sql += " AND created_at <= ?"
            params.append(before)
        sql += " ORDER BY seq DESC LIMIT ?"
        params.append(limit)
        return [{**dict(r), "evidence": json.loads(r["evidence_json"])} for r in self.q(sql, tuple(params))]

    def traces(self, aid: str, limit: int, before: str | None) -> list[dict[str, Any]]:
        sql = "SELECT id, sim_time, purpose, json FROM retrieval_traces WHERE agent_id=?"
        params: list[Any] = [aid]
        if before:
            sql += " AND sim_time <= ?"
            params.append(before)
        sql += " ORDER BY sim_time DESC, id DESC LIMIT ?"
        params.append(limit)
        out = []
        for r in self.q(sql, tuple(params)):
            t = json.loads(r["json"])
            out.append(
                {
                    "id": r["id"],
                    "sim_time": r["sim_time"],
                    "purpose": r["purpose"],
                    "query": t["query"],
                    "delivered": len(t["delivered"]),
                    "candidates": t.get("candidates_total", len(t["candidates"])),
                }
            )
        return out

    def trace(self, trace_id: str) -> dict[str, Any]:
        r = self.one("SELECT json FROM retrieval_traces WHERE id=?", (trace_id,))
        if r is None:
            raise KeyError(trace_id)
        t = json.loads(r["json"])
        t["id"] = trace_id
        w = t["weights"]
        for c in t["candidates"]:
            n = c["normalized"]
            c["weighted"] = {k: (w.get(k, 1.0) * v if v is not None else None) for k, v in n.items()}
        if len(t["candidates"]) >= 2:
            a, b = t["candidates"][0], t["candidates"][1]
            diffs = {k: (a["weighted"][k] or 0) - (b["weighted"][k] or 0) for k in a["weighted"]}
            lead = max(diffs, key=lambda k: diffs[k])
            t["explain_top2"] = {"a": a["id"], "b": b["id"], "difference": diffs, "score_difference": a["score"] - b["score"], "largest_push": lead}
        return t

    def evidence(self, memory_id: str) -> dict[str, Any]:
        with self.lock:
            return evidence_tree(self.store, memory_id)

    def reflections(self, aid: str, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.q(
            "SELECT id, description, created_at, depth, evidence_json, metadata_json FROM memories WHERE owner_id=? AND kind='reflection' ORDER BY seq DESC LIMIT ?",
            (aid, limit),
        )
        return [
            {
                "id": r["id"],
                "description": r["description"],
                "created_at": r["created_at"],
                "depth": r["depth"],
                "evidence": json.loads(r["evidence_json"]),
                "question": json.loads(r["metadata_json"]).get("question"),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------ conversations, events, evaluation
    def conversations(self, aid: str | None) -> list[dict[str, Any]]:
        rows = self.q("SELECT json FROM conversations ORDER BY started_at, id")
        out = []
        for r in rows:
            c = json.loads(r["json"])
            if aid and aid not in c["participants"]:
                continue
            out.append(
                {k: c.get(k) for k in ("id", "participants", "initiator_id", "started_at", "ended_at", "location", "summary", "status", "reason")}
                | {"utterances": len(c.get("utterances", []))}
            )
        return out

    def conversation(self, cid: str) -> dict[str, Any]:
        r = self.one("SELECT json FROM conversations WHERE id=?", (cid,))
        if r is None:
            raise KeyError(cid)
        return json.loads(r["json"])

    def events(self, type_: str | None, aid: str | None, limit: int, after_id: int) -> list[dict[str, Any]]:
        sql = "SELECT id, step, sim_time, type, agent_id, json FROM events WHERE id > ?"
        params: list[Any] = [after_id]
        if type_:
            sql += " AND type=?"
            params.append(type_)
        if aid:
            sql += " AND agent_id=?"
            params.append(aid)
        sql += " ORDER BY id LIMIT ?"
        params.append(limit)
        return [
            {"id": r["id"], "step": r["step"], "sim_time": r["sim_time"], "type": r["type"], "agent_id": r["agent_id"], **json.loads(r["json"])}
            for r in self.q(sql, tuple(params))
        ]

    # ------------------------------------------------------------------ provenance and diffusion
    def manifest(self) -> dict[str, Any]:
        path = self.run_dir / "manifest.json"
        return json.loads(path.read_text()) if path.exists() else {}

    def _ledger(self) -> Any:
        import sqlite3

        path = self.run_dir / "provider.sqlite"
        if not path.exists():
            return None
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def calls(self, *, task: str | None, agent: str | None, limit: int, before: int | None) -> list[dict[str, Any]]:
        """Recorded model calls, newest first (what was asked, of which model, with what result)."""

        conn = self._ledger()
        if conn is None:
            return []
        sql = (
            "SELECT id, scope, step, sim_time, task, template_id, agent_id, purpose, provider, model, served_model, status, "
            "attempt_kind, input_tokens, output_tokens, tokens_estimated, cost_usd, latency_ms FROM calls WHERE 1=1"
        )
        params: list[Any] = []
        if task:
            sql += " AND task=?"
            params.append(task)
        if agent:
            sql += " AND agent_id=?"
            params.append(agent)
        if before:
            sql += " AND id < ?"
            params.append(before)
        rows = [dict(r) for r in conn.execute(sql + " ORDER BY id DESC LIMIT ?", (*params, limit))]
        conn.close()
        return rows

    def call(self, call_id: int) -> dict[str, Any]:
        conn = self._ledger()
        if conn is None:
            raise KeyError(call_id)
        row = conn.execute("SELECT * FROM calls WHERE id=?", (call_id,)).fetchone()
        conn.close()
        if row is None:
            raise KeyError(call_id)
        d = dict(row)
        for k in ("settings_json", "schema_json", "metadata_json", "parsed_json", "validation_errors"):
            if d.get(k):
                try:
                    d[k] = json.loads(d[k])
                except ValueError:
                    pass
        return d

    def diffusion(self) -> dict[str, Any]:
        """Who has received word of each seeded event, from whom, and every transmission (researcher only)."""

        from ..evaluation.diffusion import transmissions
        from ..evaluation.evidence import load_topics, topic_evidence
        from ..scenario.loader import load_scenario

        sc = load_scenario(repo_path(self.cfg.scenario.path), population=self.cfg.scenario.population)
        topics = load_topics(sc.events)
        agents = [r["id"] for r in self.q("SELECT id FROM agents ORDER BY order_index")]
        out: dict[str, Any] = {}
        with self.lock:
            for key, topic in topics.items():
                per = {}
                for aid in agents:
                    ev = topic_evidence(self.db, aid, topic)
                    strong = [e for e in ev if e["strong"]]
                    first = strong[0] if strong else None
                    per[aid] = {
                        "aware": bool(strong),
                        "seeded": any(e["origin"] == "seed" for e in strong),
                        "first": {k: first[k] for k in ("created_at", "origin", "speaker_id", "conversation_id", "text")} if first else None,
                        "evidence": len(strong),
                        "weak": len(ev) - len(strong),
                    }
                out[key] = {
                    "label": sc.events[key].get("label", key),
                    "agents": per,
                    "transmissions": transmissions(self.db, topic),
                }
        return out

    def evaluation(self) -> dict[str, Any] | None:
        base = self.run_dir / "exports" / "evaluation"
        if not (base / "summary.json").exists():
            return None
        out: dict[str, Any] = {"summary": json.loads((base / "summary.json").read_text())}
        for name in ("failures.json",):
            if (base / name).exists():
                out["failures"] = json.loads((base / name).read_text())
        for name, key in (("diffusion.jsonl", "diffusion"), ("relationships.jsonl", "relationships")):
            p = base / name
            if p.exists():
                out[key] = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
        import csv

        for name, key in (("attendance.csv", "attendance"), ("transmissions.csv", "transmissions")):
            p = base / name
            if p.exists():
                out[key] = list(csv.DictReader(p.open()))
        return out

    def interviews(self) -> dict[str, Any]:
        base = self.run_dir / "exports" / "interviews"
        sets = {}
        if base.exists():
            for d in sorted(base.iterdir()):
                if (d / "responses.jsonl").exists():
                    rows = [json.loads(line) for line in (d / "responses.jsonl").read_text().splitlines() if line.strip()]
                    manifest = json.loads((d / "manifest.json").read_text()) if (d / "manifest.json").exists() else {}
                    analysis = json.loads((d / "blinded" / "analysis.json").read_text()) if (d / "blinded" / "analysis.json").exists() else None
                    sets[d.name] = {"manifest": manifest, "responses": rows, "analysis": analysis}
        return sets
