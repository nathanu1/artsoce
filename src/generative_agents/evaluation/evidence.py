"""Evaluator-side topic matching and memory evidence (spec N-1 … N-4).

Everything here reads scenario ground truth (``events.yaml``) and finished run data. None of
it is ever rendered into an agent prompt.

Evidence of exposure is a memory the agent *received*: an authored seed, a statement heard
from someone, an inner-voice intervention or a direct observation. The agent's own
statements, reflections, plans and model-written conversation summaries are not exposure
evidence (a summary alone is reported as weak support).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..db import Database, parse_iso
from ..scenario.loader import EVENT_FLAGS
from ..schemas import MemoryOrigin

EXPOSURE_ORIGINS = {MemoryOrigin.SEED.value, MemoryOrigin.STATEMENT.value, MemoryOrigin.INNER_VOICE.value, MemoryOrigin.DIRECT_OBSERVATION.value}
WEAK_ORIGINS = {MemoryOrigin.CONVERSATION.value}


@dataclass
class Topic:
    key: str
    label: str
    originator: str | None
    keywords: list[str]
    require_all: list[str] = field(default_factory=list)
    details: dict[str, list[str]] = field(default_factory=dict)
    invitation_patterns: list[str] = field(default_factory=list)
    acceptance_patterns: list[str] = field(default_factory=list)
    probe_question: str | None = None
    place: str | None = None
    window: tuple[datetime, datetime] | None = None
    seed_flag: str | None = None  # importer flag on seed statements that carry this knowledge

    @classmethod
    def from_event(cls, key: str, ev: dict[str, Any]) -> Topic:
        w = ev.get("window")
        window = (datetime.fromisoformat(str(w["start"])), datetime.fromisoformat(str(w["end"]))) if w else None
        return cls(
            key=key,
            label=ev.get("topic") or ev.get("label") or key,
            originator=ev.get("originator"),
            keywords=list(ev.get("topic_keywords", [])),
            require_all=list(ev.get("require_all", [])),
            details=dict(ev.get("details", {})),
            invitation_patterns=list(ev.get("invitation_patterns", [])),
            acceptance_patterns=list(ev.get("acceptance_patterns", [])),
            probe_question=ev.get("probe_question"),
            place=ev.get("place"),
            window=window,
            seed_flag=EVENT_FLAGS.get(key),
        )

    def matches(self, text: str) -> bool:
        if self.require_all:
            return all(re.search(p, text, re.I) for p in self.require_all)
        return any(re.search(re.escape(k), text, re.I) for k in self.keywords)

    def details_in(self, text: str) -> list[str]:
        return sorted(d for d, pats in self.details.items() if any(re.search(p, text, re.I) for p in pats))

    def is_invitation(self, text: str) -> bool:
        return self.matches(text) and any(re.search(p, text, re.I) for p in self.invitation_patterns)

    def is_acceptance(self, text: str) -> bool:
        return any(re.search(p, text, re.I) for p in self.acceptance_patterns)


def load_topics(events: dict[str, Any]) -> dict[str, Topic]:
    return {k: Topic.from_event(k, v) for k, v in (events or {}).items()}


def topic_evidence(db: Database, agent_id: str, topic: Topic, before: datetime | None = None) -> list[dict[str, Any]]:
    """Memories of ``agent_id`` that show it received information about ``topic``."""

    out = []
    for r in db.query(
        "SELECT id, origin, description, created_at, speaker_id, conversation_id, seed, metadata_json FROM memories WHERE owner_id=? ORDER BY seq",
        (agent_id,),
    ):
        if r["origin"] not in EXPOSURE_ORIGINS and r["origin"] not in WEAK_ORIGINS:
            continue
        created = parse_iso(r["created_at"])
        if before is not None and created is not None and created > before:
            continue
        text = r["description"]
        flagged = bool(r["seed"]) and topic.seed_flag is not None and topic.seed_flag in (json.loads(r["metadata_json"] or "{}").get("flags") or [])
        if not (topic.matches(text) or flagged):
            continue
        out.append(
            {
                "memory_id": r["id"],
                "origin": r["origin"],
                "strong": r["origin"] in EXPOSURE_ORIGINS,
                "created_at": r["created_at"],
                "speaker_id": r["speaker_id"],
                "conversation_id": r["conversation_id"],
                "details": topic.details_in(text),
                "text": text,
            }
        )
    return out


def person_evidence(db: Database, agent_id: str, other_id: str, other_name: str, before: datetime | None = None) -> list[dict[str, Any]]:
    """Seed or interaction records that let ``agent_id`` know of ``other``."""

    first = other_name.split()[0]
    out = []
    for r in db.query("SELECT id, origin, description, created_at, speaker_id, conversation_id FROM memories WHERE owner_id=? ORDER BY seq", (agent_id,)):
        created = parse_iso(r["created_at"])
        if before is not None and created is not None and created > before:
            continue
        text = r["description"]
        origin = r["origin"]
        if r["speaker_id"] == other_id:
            kind = "heard_from"
        elif origin == MemoryOrigin.SEED.value and (other_name in text or re.search(rf"\b{re.escape(first)}\b", text)):
            kind = "seed"
        elif (
            origin in (MemoryOrigin.STATEMENT.value, MemoryOrigin.OWN_STATEMENT.value, MemoryOrigin.CONVERSATION.value, MemoryOrigin.INNER_VOICE.value)
            and other_name in text
        ):
            kind = "conversation"
        elif origin == MemoryOrigin.DIRECT_OBSERVATION.value and text.startswith(other_name):
            kind = "observed"
        else:
            continue
        out.append({"memory_id": r["id"], "kind": kind, "origin": origin, "created_at": r["created_at"], "text": text})
    return out


def conversations(db: Database) -> list[dict[str, Any]]:
    rows = [json.loads(r["json"]) for r in db.query("SELECT json FROM conversations")]
    return sorted(rows, key=lambda c: (c["started_at"], c["id"]))
