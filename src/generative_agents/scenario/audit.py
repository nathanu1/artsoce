"""Scenario audit (spec A-1 … A-7, J-8): what each agent starts with, checked against the map.

The audit is evaluator-side: it reads seeds, identity flags and the world, and writes a JSON
report. It never changes scenario files.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from ..world.hierarchy import tree_addresses
from .loader import EVENT_FLAGS, Scenario


def audit_scenario(sc: Scenario) -> dict[str, Any]:
    w = sc.world
    real = set(w.address_tiles)
    issues: list[str] = []
    agents: dict[str, Any] = {}
    spawn = Counter()
    holders: dict[str, list[dict[str, Any]]] = {flag: [] for flag in EVENT_FLAGS.values()}
    all_seed_texts = Counter()
    for aid in sc.agent_ids:
        a = sc.agents[aid]
        texts = [s.text for s in a.seeds]
        dup = [t for t, n in Counter(texts).items() if n > 1]
        all_seed_texts.update(set(texts))
        known = tree_addresses(a.spatial_memory)
        unknown = sorted(x for x in known if x not in real)
        tile = tuple(a.initial_tile) if a.initial_tile else None
        if tile is None or not w.walkable(*tile):
            issues.append(f"{aid}: initial tile {tile} is not walkable")
        else:
            spawn[tile] += 1
        if not w.exists(a.identity.living_area):
            issues.append(f"{aid}: living area {a.identity.living_area} is not on the map")
        if dup:
            issues.append(f"{aid}: duplicated seed statements {dup}")
        if unknown:
            issues.append(f"{aid}: spatial memory names places that are not on the map: {unknown[:5]}")
        for flag in holders:
            where = [f"seed {s.index}" for s in a.seeds if flag in s.flags]
            if flag in a.identity_flags:
                where.append("identity")
            if where:
                holders[flag].append({"agent": aid, "where": where})
        agents[aid] = {
            "name": a.identity.name,
            "seeds": len(a.seeds),
            "initial_tile": tile,
            "living_area": a.identity.living_area,
            "known_places": {
                "sectors": sum(1 for x in known if x.count(":") == 1),
                "arenas": sum(1 for x in known if x.count(":") == 2),
                "objects": sum(1 for x in known if x.count(":") == 3),
            },
            "perception": a.perception,
        }
    shared = [list(t) for t, n in spawn.items() if n > 1]
    if shared:
        issues.append(f"agents share spawn tiles {shared}")
    originators = {k: v.get("originator") for k, v in sc.events.items()}
    for key, flag in EVENT_FLAGS.items():
        origin = originators.get(key)
        others = [h["agent"] for h in holders[flag] if h["agent"] != origin]
        if others:
            issues.append(f"{flag}: held by non-originators {others} (policy {sc.candidacy_seed_policy})")
    return {
        "scenario": sc.name,
        "agents": len(sc.agent_ids),
        "unique_ids": len(set(sc.agent_ids)) == len(sc.agent_ids),
        "unique_names": len({sc.agents[a].identity.name for a in sc.agent_ids}) == len(sc.agent_ids),
        "map": w.describe(),
        "knowledge_holders": holders,
        "originators": originators,
        "seed_policy": sc.candidacy_seed_policy,
        "seed_policy_log": sc.seed_policy_log,
        "seed_statements_shared_by_agents": sum(1 for n in all_seed_texts.values() if n > 1),
        "per_agent": agents,
        "issues": issues,
        "ok": not issues,
    }
