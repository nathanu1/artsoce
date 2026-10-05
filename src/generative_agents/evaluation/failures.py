"""Failure taxonomy with preserved examples (paper §6.5, §7.2; spec N-4).

Categories (prompt §9): missed exposure, retrieval failure despite stored evidence,
unsupported embellishment, ungrounded inference, stale location knowledge, invalid
action/location, forgotten commitment, schedule conflict, and overly agreeable or formal
behavior. Each is computed from run records and probe results with an explicit rule; the
last one is a text heuristic and labeled as such. Examples are kept for qualitative review.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from ..db import Database, parse_iso
from ..world.constraints import Constraints
from ..world.hierarchy import WorldMap
from .evidence import conversations

FORMAL = [
    r"it was (good|nice|great|a pleasure) (talking|speaking|chatting) (to|with) you",
    r"\bas always\b",
    r"have a (wonderful|great|lovely) (day|evening)",
    r"\bpleasure\b",
]
AGREE = [r"\bthat sounds (wonderful|great|lovely|amazing|like a great idea)\b", r"\bi'?d love to\b", r"\babsolutely\b", r"\bwhat a (great|wonderful) idea\b"]
CATEGORIES = [
    "missed_exposure",
    "retrieval_failure",
    "unsupported_embellishment",
    "ungrounded_inference",
    "stale_location_knowledge",
    "invalid_action_location",
    "forgotten_commitment",
    "schedule_conflict",
    "overly_agreeable_or_formal",
]


def _add(out: dict[str, Any], cat: str, example: dict[str, Any], keep: int) -> None:
    out[cat]["count"] += 1
    if len(out[cat]["examples"]) < keep:
        out[cat]["examples"].append(example)


def norm_violations(db: Database, world: WorldMap, constraints: Constraints, identities: dict[str, Any]) -> list[dict[str, Any]]:
    """Frames where an agent is somewhere strict-v1 would refuse (computed even when it was off)."""

    if not constraints.opening_hours and not constraints.single_occupancy and not constraints.private_patterns:
        return []
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    pos: dict[str, tuple[int, int]] = {}
    for r in db.query("SELECT step, sim_time, json FROM frames ORDER BY step"):
        f = json.loads(r["json"])
        if f.get("key"):
            pos = {}
        for aid, v in f["agents"].items():
            if v[0] is not None:
                pos[aid] = (v[0], v[1])
        now = parse_iso(r["sim_time"])
        arenas: dict[str, set[str]] = defaultdict(set)
        for aid, p in pos.items():
            a = world.arena_at(*p)
            if a:
                arenas[a].add(aid)
        for aid, p in pos.items():
            ident = identities.get(aid)
            addr = world.arena_at(*p) or world.sector_at(*p)
            if ident is None or not addr:
                continue
            v = constraints.check(ident, addr, now, arenas, current_arena=None)  # check() ignores the agent itself
            if not v.allowed:
                key = (aid, v.rule or "", addr)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"agent_id": aid, "rule": v.rule, "address": addr, "time": r["sim_time"], "message": v.message})
    return out


def taxonomy(
    db: Database,
    *,
    diffusion_rows: list[dict[str, Any]] | None = None,
    relationship_rows: list[dict[str, Any]] | None = None,
    attendance_report: dict[str, Any] | None = None,
    world: WorldMap | None = None,
    reference_constraints: Constraints | None = None,
    identities: dict[str, Any] | None = None,
    keep: int = 5,
) -> dict[str, Any]:
    out: dict[str, Any] = {c: {"count": 0, "examples": [], "rule": ""} for c in CATEGORIES}
    out["missed_exposure"]["rule"] = "probe: no received memory about the event (status unaware)"
    out["retrieval_failure"]["rule"] = "probe: received memory exists but the answer denies or does not know"
    out["unsupported_embellishment"]["rule"] = "probe: claimed details (date/time/place/...) not present in any received memory"
    out["ungrounded_inference"]["rule"] = "probe: claims knowledge with no received memory (event or person)"
    out["stale_location_knowledge"]["rule"] = (
        "action: the object's lasting condition when the agent chose it differed from the condition the agent last saw (in-use overlays ignored)"
    )
    out["invalid_action_location"]["rule"] = "engine: failed location/route, refused by strict-v1, or (policy none) a position strict-v1 would refuse"
    out["forgotten_commitment"]["rule"] = "accepted an invitation but never scheduled the event"
    out["schedule_conflict"]["rule"] = "invited or accepted, and the plan for the event window holds something else"
    out["overly_agreeable_or_formal"]["rule"] = "heuristic: formal closings / reflexive agreement phrases in utterances (text patterns, not a judgment)"
    for r in diffusion_rows or []:
        ex = {"event": r["event"], "agent_id": r["agent_id"], "answer": r["answer"], "evidence": [e["memory_id"] for e in r["evidence"]][:5]}
        if r["status"] == "unaware":
            _add(out, "missed_exposure", ex, keep)
        elif r["status"] == "retrieval_failure":
            _add(out, "retrieval_failure", ex, keep)
        elif r["status"] == "claimed_unsupported":
            _add(out, "ungrounded_inference", ex, keep)
        if r.get("unsupported_details"):
            _add(out, "unsupported_embellishment", {**ex, "details": r["unsupported_details"]}, keep)
    for r in relationship_rows or []:
        if r["status"] == "hallucinated":
            _add(out, "ungrounded_inference", {"asker": r["asker"], "about": r["about"], "answer": r["answer"]}, keep)
    for e in db.query("SELECT sim_time, agent_id, json FROM events WHERE type IN ('action', 'action_failure', 'constraint') ORDER BY id"):
        d = json.loads(e["json"])
        if d.get("seen_lasting") is not None and d.get("actual_lasting") is not None and d["seen_lasting"] != d["actual_lasting"]:
            _add(
                out,
                "stale_location_knowledge",
                {
                    "agent_id": e["agent_id"],
                    "time": e["sim_time"],
                    "address": d.get("address"),
                    "last_seen_condition": d["seen_lasting"],
                    "actual_condition": d["actual_lasting"],
                },
                keep,
            )
        if "reason" in d and d.get("activity"):  # action_failure
            _add(out, "invalid_action_location", {"agent_id": e["agent_id"], "time": e["sim_time"], "activity": d["activity"], "reason": d["reason"]}, keep)
        if "rule" in d and "message" in d:  # constraint refusal
            _add(out, "invalid_action_location", {"agent_id": e["agent_id"], "time": e["sim_time"], "rule": d["rule"], "message": d["message"]}, keep)
    if world is not None and reference_constraints is not None and identities is not None:
        for v in norm_violations(db, world, reference_constraints, identities):
            _add(out, "invalid_action_location", {"norm_violation": True, **v}, keep)
    if attendance_report:
        for r in attendance_report["rows"]:
            if r["host"]:
                continue
            if r["accepted"] and not r["scheduled"]:
                _add(
                    out, "forgotten_commitment", {"agent_id": r["agent_id"], "acceptance": r["acceptance"], "plans_in_window": r["other_plans_in_window"]}, keep
                )
            if (r["invited"] or r["accepted"]) and not r["scheduled"] and r["other_plans_in_window"]:
                _add(out, "schedule_conflict", {"agent_id": r["agent_id"], "plans_in_window": r["other_plans_in_window"]}, keep)
    total_utt = 0
    for c in conversations(db):
        for u in c.get("utterances", []):
            total_utt += 1
            t = u["text"].lower()
            hits = [p for p in FORMAL + AGREE if re.search(p, t)]
            if hits:
                _add(out, "overly_agreeable_or_formal", {"conversation_id": c["id"], "speaker": u["speaker_id"], "text": u["text"], "patterns": hits}, keep)
    out["overly_agreeable_or_formal"]["denominator_utterances"] = total_utt
    return out
