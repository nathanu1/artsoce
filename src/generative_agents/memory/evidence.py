"""Structural checks on reflection evidence (spec E-6, E-7).

These checks prove that a cited memory exists, belongs to the reflecting agent, was among the
memories supplied to that prompt, and that citations form no cycle. They do not prove that an
inference is semantically justified; insights are stored as generated, for review.
"""

from __future__ import annotations

from typing import Any

from .store import MemoryStore


def validate_evidence(store: MemoryStore, owner_id: str, evidence_ids: list[str], supplied_ids: set[str]) -> list[str]:
    errors: list[str] = []
    if not evidence_ids:
        errors.append("an insight must cite at least one supplied memory")
    found = {m.id: m for m in store.get_many(evidence_ids)}
    for mid in evidence_ids:
        mem = found.get(mid)
        if mem is None:
            errors.append(f"cited memory {mid} does not exist")
        elif mem.owner_id != owner_id:
            errors.append(f"cited memory {mid} belongs to another agent")
        elif mid not in supplied_ids:
            errors.append(f"cited memory {mid} was not supplied in this prompt")
    return errors


def depth_for(store: MemoryStore, evidence_ids: list[str]) -> int:
    """1 + deepest cited memory (released associative_memory.py:207-212)."""

    mems = store.get_many(evidence_ids)
    return 1 + max((m.depth for m in mems), default=0)


def has_cycle(store: MemoryStore, start_id: str, limit: int = 10_000) -> bool:
    """True if following evidence links from ``start_id`` ever returns to a node on the path."""

    path: set[str] = set()
    done: set[str] = set()

    def visit(mid: str, budget: list[int]) -> bool:
        budget[0] -= 1
        if budget[0] < 0:
            return True
        if mid in path:
            return True
        if mid in done:
            return False
        path.add(mid)
        mem = store.get(mid)
        for child in mem.evidence_ids if mem else []:
            if visit(child, budget):
                return True
        path.discard(mid)
        done.add(mid)
        return False

    return visit(start_id, [limit])


def evidence_tree(store: MemoryStore, memory_id: str, max_depth: int = 6) -> dict[str, Any]:
    """Nested evidence tree for the viewer (leaves are observations or plans)."""

    def build(mid: str, depth: int, seen: frozenset[str]) -> dict[str, Any]:
        mem = store.get(mid)
        if mem is None:
            return {"id": mid, "missing": True}
        node: dict[str, Any] = {
            "id": mem.id,
            "kind": mem.kind.value,
            "origin": mem.origin.value,
            "description": mem.description,
            "importance": mem.importance,
            "created_at": mem.created_at.isoformat(),
            "depth": mem.depth,
            "evidence": [],
        }
        if depth < max_depth:
            for child in mem.evidence_ids:
                if child in seen:
                    node["evidence"].append({"id": child, "cycle": True})
                else:
                    node["evidence"].append(build(child, depth + 1, seen | {child}))
        elif mem.evidence_ids:
            node["truncated"] = len(mem.evidence_ids)
        return node

    return build(memory_id, 0, frozenset({memory_id}))
