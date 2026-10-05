"""Information diffusion (paper §7.1.1 p. 15; spec N-1).

Every agent is asked the paper's probe question on a clone of a snapshot. The answer is
labeled "claims knowledge" by the ``awareness`` classifier (the paper labeled by hand; the
automated label is our adaptation) and then checked against the agent's own memory:

* ``aware``: claims it, and a received memory supports it;
* ``claimed_unsupported``: claims it without any received memory (hallucination);
* ``retrieval_failure``: has the evidence but does not claim it;
* ``unaware``: neither.

Separately, conversation transcripts give every transmission (time, sender, receiver,
conversation, which details were said). The originator is counted in population
percentages and reported apart from newly informed agents.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..db import Database
from ..providers.base import TaskFailed
from .evidence import Topic, conversations, topic_evidence
from .interview import InterviewSession


def transmissions(db: Database, topic: Topic) -> list[dict[str, Any]]:
    out = []
    for c in conversations(db):
        parts = c["participants"]
        for i, u in enumerate(c.get("utterances", [])):
            if not topic.matches(u["text"]):
                continue
            receiver = next((p for p in parts if p != u["speaker_id"]), None)
            out.append(
                {
                    "event": topic.key,
                    "time": u.get("sim_time") or c["started_at"],
                    "conversation_id": c["id"],
                    "turn": i,
                    "sender": u["speaker_id"],
                    "receiver": receiver,
                    "details": topic.details_in(u["text"]),
                    "invitation": topic.is_invitation(u["text"]),
                    "text": u["text"],
                }
            )
    return out


def first_exposures(trans: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    first: dict[str, dict[str, Any]] = {}
    for t in trans:
        r = t["receiver"]
        if r and r not in first:
            first[r] = t
    return first


def classify(
    session: InterviewSession, agent_id: str, question: str, answer: str, topic_label: str, keywords: list[str], details: dict[str, list[str]]
) -> dict[str, Any]:
    try:
        out = session.svc.gateway.run(
            "awareness",
            {
                "question": question,
                "answer": answer,
                "topic": topic_label,
                "details": ", ".join(sorted(details)) or "(none)",
                "_answer": answer,
                "_topic_keywords": keywords,
                "_detail_patterns": details,
            },
            agent_id=agent_id,
            sim_time=session.now,
            purpose="evaluation:awareness",
        )
    except TaskFailed as exc:
        return {"claims_knowledge": None, "details": [], "quote": "", "label_error": str(exc)}
    o = out.output
    return {"claims_knowledge": bool(o.claims_knowledge), "details": [d for d in o.details if d in details], "quote": o.quote}


def probe_awareness(session: InterviewSession, topic: Topic, agents: list[str], *, before: datetime | None = None) -> list[dict[str, Any]]:
    if not topic.probe_question:
        raise ValueError(f"event {topic.key} has no probe_question")
    rows = []
    for aid in agents:
        ans = session.ask(aid, topic.probe_question)
        label = classify(session, aid, topic.probe_question, ans.answer, topic.label, topic.keywords or [topic.label], topic.details)
        ev = topic_evidence(session.db, aid, topic, before=before or session.now)
        strong = [e for e in ev if e["strong"]]
        claimed = label["claims_knowledge"]
        supported = bool(strong)
        if claimed is None:
            status = "label_failed"
        elif claimed and supported:
            status = "aware"
        elif claimed:
            status = "claimed_unsupported"
        elif supported:
            status = "retrieval_failure"
        else:
            status = "unaware"
        evidence_details = sorted({d for e in ev for d in e["details"]})  # what the agent's records say, incl. summaries
        rows.append(
            {
                "event": topic.key,
                "agent_id": aid,
                "originator": aid == topic.originator,
                "question": topic.probe_question,
                "answer": ans.answer,
                "claims_knowledge": claimed,
                "claimed_details": label["details"],
                "quote": label.get("quote", ""),
                "supported": supported,
                "weak_support_only": not supported and bool(ev),
                "evidence": [{k: e[k] for k in ("memory_id", "origin", "created_at", "speaker_id", "conversation_id", "details", "text")} for e in ev],
                "evidence_details": evidence_details,
                "unsupported_details": sorted(set(label["details"]) - set(evidence_details)) if claimed else [],
                "first_exposure": strong[0]["created_at"] if strong else None,
                "first_source": strong[0]["speaker_id"] if strong else None,
                "status": status,
                "reference_time": session.now.isoformat(),
                "call_ids": ans.call_ids,
            }
        )
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    claimed = [r for r in rows if r["claims_knowledge"]]
    aware = [r for r in rows if r["status"] == "aware"]
    origin = [r for r in rows if r["originator"]]
    return {
        "n": n,
        "claimed": len(claimed),
        "claimed_pct": round(100 * len(claimed) / n, 1),
        "supported_aware": len(aware),
        "supported_aware_pct": round(100 * len(aware) / n, 1),
        "originator_included": bool(origin),
        "newly_informed_supported": len([r for r in aware if not r["originator"]]),
        "claimed_unsupported": len([r for r in rows if r["status"] == "claimed_unsupported"]),
        "retrieval_failures": len([r for r in rows if r["status"] == "retrieval_failure"]),
        "label_failures": len([r for r in rows if r["status"] == "label_failed"]),
    }
