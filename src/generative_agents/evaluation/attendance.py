"""Coordination: who actually showed up (paper §7.1 p. 16; spec N-3).

Attendance is physical presence: an agent counts as present when its recorded position is
inside the event's place for at least ``min_minutes`` during the event window (from the run's
frames, never from interviews). Exposure, invitation, accepted intention, scheduled action and
arrival are separate variables. The host is excluded from every guest denominator.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from ..db import Database, parse_iso
from ..world.hierarchy import WorldMap
from .evidence import Topic, conversations, topic_evidence


def presence_minutes(db: Database, world: WorldMap, place: str, start: datetime, end: datetime, seconds_per_step: int) -> dict[str, float]:
    tiles = set(world.tiles_for(place))
    if not tiles:
        raise ValueError(f"unknown place {place}")
    frames = db.query("SELECT step, sim_time, json FROM frames ORDER BY step")
    if not frames:
        raise ValueError("this run recorded no frames (output.record_frames=false); attendance cannot be measured")
    pos: dict[str, tuple[int, int]] = {}
    minutes: dict[str, float] = {}
    rows = [(r["step"], parse_iso(r["sim_time"]), json.loads(r["json"])) for r in frames]
    # each frame describes the state after its step; it holds until the next frame
    for i, (_step, t, f) in enumerate(rows):
        agents = f["agents"]
        if f.get("key"):
            pos = {}
        for aid, v in agents.items():
            if v[0] is not None:
                pos[aid] = (v[0], v[1])
        t0 = t
        t1 = rows[i + 1][1] if i + 1 < len(rows) else t + timedelta(seconds=seconds_per_step)
        lo, hi = max(t0, start), min(t1, end)
        if hi <= lo:
            continue
        span = (hi - lo).total_seconds() / 60
        for aid, p in pos.items():
            if p in tiles:
                minutes[aid] = minutes.get(aid, 0.0) + span
    return minutes


def attendance(
    db: Database, world: WorldMap, topic: Topic, agents: list[str], *, host: str | None, seconds_per_step: int, min_minutes: float = 10.0
) -> dict[str, Any]:
    if topic.window is None or topic.place is None:
        raise ValueError(f"event {topic.key} needs a place and a window")
    start, end = topic.window
    present = presence_minutes(db, world, topic.place, start, end, seconds_per_step)
    convs = conversations(db)
    invited: dict[str, dict[str, Any]] = {}
    accepted: dict[str, dict[str, Any]] = {}
    for c in convs:
        if parse_iso(c["started_at"]) and parse_iso(c["started_at"]) >= end:
            continue
        invited_here: set[str] = set()
        for u in c.get("utterances", []):
            listener = next((p for p in c["participants"] if p != u["speaker_id"]), None)
            if topic.is_invitation(u["text"]) and listener:
                invited_here.add(listener)
                if listener not in invited:
                    invited[listener] = {"by": u["speaker_id"], "conversation_id": c["id"], "time": c["started_at"], "text": u["text"]}
            # an acceptance answers an invitation made to the speaker earlier in this conversation
            if u["speaker_id"] in invited_here and topic.is_acceptance(u["text"]) and u["speaker_id"] not in accepted:
                accepted[u["speaker_id"]] = {"conversation_id": c["id"], "time": c["started_at"], "text": u["text"]}
    day = start.date().isoformat()
    rows = []
    for aid in agents:
        ev = [e for e in topic_evidence(db, aid, topic, before=end) if e["strong"]]
        plans = [json.loads(r["json"]) for r in db.query("SELECT json FROM plans WHERE agent_id=? AND day=? AND level IN ('hour','task')", (aid, day))]
        overlapping = [p for p in plans if parse_iso(p["start"]) < end and parse_iso(p["start"]) + timedelta(minutes=p["duration_min"]) > start]
        scheduled = [p for p in overlapping if topic.matches(p["description"]) and p["status"] != "superseded"]
        planned_else = sorted({p["description"] for p in overlapping if p["level"] == "hour" and not topic.matches(p["description"])})
        mins = round(present.get(aid, 0.0), 1)
        rows.append(
            {
                "agent_id": aid,
                "host": aid == host,
                "exposed": bool(ev),
                "first_exposure": ev[0]["created_at"] if ev else None,
                "exposed_before_start": bool(ev) and parse_iso(ev[0]["created_at"]) < start,
                "invited": aid in invited,
                "invitation": invited.get(aid),
                "accepted": aid in accepted,
                "acceptance": accepted.get(aid),
                "scheduled": bool(scheduled),
                "scheduled_items": [p["description"] for p in scheduled][:3],
                "other_plans_in_window": planned_else[:3],
                "present_minutes": mins,
                "attended": mins >= min_minutes,
            }
        )
    guests = [r for r in rows if not r["host"]]

    def rate(group: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(group)
        k = len([r for r in group if r["attended"]])
        return {"attended": k, "n": n, "rate": round(k / n, 3) if n else None}

    return {
        "event": topic.key,
        "place": topic.place,
        "window": [start.isoformat(), end.isoformat()],
        "min_minutes": min_minutes,
        "host": host,
        "rows": rows,
        "summary": {
            "present_guests": len([r for r in guests if r["attended"]]),
            "host_present": any(r["attended"] for r in rows if r["host"]),
            "among_invited": rate([r for r in guests if r["invited"]]),
            "among_exposed": rate([r for r in guests if r["exposed"]]),
            "among_accepted": rate([r for r in guests if r["accepted"]]),
            "among_scheduled": rate([r for r in guests if r["scheduled"]]),
            "uninvited_present": len([r for r in guests if r["attended"] and not r["invited"]]),
            "denominators_exclude_host": True,
        },
    }
