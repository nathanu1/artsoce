"""Relationship formation (paper §7.1.1 pp. 15–16; spec N-2).

Each agent is asked "Do you know of <name>?" about every other agent, at the start and at
the end. An answer counts as supported when the asker's memory has the other person in an
authored seed or an interaction record (a statement heard from them, or a conversation or
statement naming them). Having only *seen* someone is reported separately and does not
support an edge. An undirected edge requires mutual supported knowledge; the paper-style
edge (both say yes, no validation) is reported next to it.

Density is ``2|E| / (n(n − 1))``; with fewer than two agents it is undefined (``None``).
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

from .diffusion import classify
from .evidence import person_evidence
from .interview import InterviewSession

QUESTION = "Do you know of {name}?"


def density(n: int, edges: int) -> float | None:
    if n < 2:
        return None
    return 2 * edges / (n * (n - 1))


def probe_relationships(session: InterviewSession, agents: list[str]) -> list[dict[str, Any]]:
    names = {a: session.identities[a].name for a in agents}
    rows = []
    for a in agents:
        for b in agents:
            if a == b:
                continue
            q = QUESTION.format(name=names[b])
            ans = session.ask(a, q)
            first, last = names[b].split()[0], names[b].split()[-1]
            label = classify(session, a, q, ans.answer, names[b], [first, last], {})
            ev = person_evidence(session.db, a, b, names[b], before=session.now)
            interaction = [e for e in ev if e["kind"] in ("seed", "heard_from", "conversation")]
            observed = [e for e in ev if e["kind"] == "observed"]
            claimed = label["claims_knowledge"]
            if claimed is None:
                status = "label_failed"
            elif claimed and interaction:
                status = "supported"
            elif claimed and observed:
                status = "observed_only"
            elif claimed:
                status = "hallucinated"
            else:
                status = "denies"
            rows.append(
                {
                    "asker": a,
                    "about": b,
                    "question": q,
                    "answer": ans.answer,
                    "claims_knowledge": claimed,
                    "status": status,
                    "evidence_kinds": sorted({e["kind"] for e in ev}),
                    "evidence_ids": [e["memory_id"] for e in interaction[:5]],
                    "reference_time": session.now.isoformat(),
                }
            )
    return rows


def graph(rows: list[dict[str, Any]], agents: list[str]) -> dict[str, Any]:
    by = {(r["asker"], r["about"]): r for r in rows}
    supported, claimed = [], []
    for a, b in combinations(sorted(agents), 2):
        ra, rb = by.get((a, b)), by.get((b, a))
        if not ra or not rb:
            continue
        if ra["status"] == "supported" and rb["status"] == "supported":
            supported.append([a, b])
        if ra["claims_knowledge"] and rb["claims_knowledge"]:
            claimed.append([a, b])
    n = len(agents)
    responses = [r for r in rows if r["claims_knowledge"] is not None]
    halluc = [r for r in responses if r["status"] == "hallucinated"]
    return {
        "n": n,
        "edges_supported": supported,
        "edges_claimed": claimed,
        "density_supported": density(n, len(supported)),
        "density_claimed": density(n, len(claimed)),
        "responses": len(responses),
        "affirmative": len([r for r in responses if r["claims_knowledge"]]),
        "hallucinated": len(halluc),
        "hallucinated_pct": round(100 * len(halluc) / len(responses), 2) if responses else None,
        "observed_only": len([r for r in responses if r["status"] == "observed_only"]),
        "density_convention": "2|E|/(n(n-1)); None when n < 2",
    }
