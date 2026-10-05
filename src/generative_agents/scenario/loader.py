"""Load a scenario directory into typed agent specs (spec A-1 … A-7, D-8).

What reaches an agent: its own identity fields, its own seed statements and its own
spatial memory. What never does: ``events.yaml`` (party window, candidacy ground truth),
which is loaded for the engine and the evaluator only (A-7).

Seed policies are applied here so both versions of the data stay auditable:

* ``candidacy_seed_policy = paper_originator_only`` (default): seed statements that carry
  knowledge of a seeded event are kept only for that event's originator (paper p. 15,
  "known only by their respective originators"). In the released n25 data this drops one
  statement, Jennifer Moore's seed 10. Every drop is listed in ``Scenario.seed_policy_log``.
* ``released_csv``: keep the released statements as they are.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml

from ..schemas import AgentIdentity
from ..world.hierarchy import WorldMap

EVENT_FLAGS = {"valentines_party": "party_knowledge", "mayor_candidacy": "candidacy_knowledge"}


@dataclass
class SeedStatement:
    index: int
    text: str
    flags: list[str] = field(default_factory=list)


@dataclass
class AgentSpec:
    id: str
    identity: AgentIdentity
    perception: dict[str, int]
    released_code: dict[str, Any]
    initial_tile: tuple[int, int] | None
    seeds: list[SeedStatement]
    spatial_memory: dict[str, Any]
    identity_flags: list[str] = field(default_factory=list)


@dataclass
class Scenario:
    name: str
    path: Path
    description: str
    source: dict[str, Any]
    start: datetime
    seconds_per_step: int
    map_path: Path
    agent_ids: list[str]
    agents: dict[str, AgentSpec]
    events: dict[str, Any]  # EVALUATOR-ONLY ground truth
    events_path: Path | None
    constraints_path: Path | None
    candidacy_seed_policy: str
    seed_policy_log: list[dict[str, Any]] = field(default_factory=list)

    @cached_property
    def world(self) -> WorldMap:
        return WorldMap.load(self.map_path)

    def identities(self) -> dict[str, AgentIdentity]:
        return {aid: self.agents[aid].identity for aid in self.agent_ids}

    def name_to_id(self) -> dict[str, str]:
        return {self.agents[a].identity.name: a for a in self.agent_ids}

    def manifest(self) -> dict[str, Any]:
        def digest(p: Path | None) -> str | None:
            return hashlib.sha256(p.read_bytes()).hexdigest() if p and p.exists() else None

        return {
            "name": self.name,
            "path": str(self.path),
            "sha256": digest(self.path),
            "map_sha256": digest(self.map_path),
            "events_sha256": digest(self.events_path),
            "constraints_sha256": digest(self.constraints_path),
            "agents": self.agent_ids,
            "agent_file_sha256": {a: self.agents[a].released_code.get("_file_sha256") for a in self.agent_ids},
            "candidacy_seed_policy": self.candidacy_seed_policy,
            "seed_policy_log": self.seed_policy_log,
            "source": self.source,
        }


def _resolve(base: Path, rel: str | None) -> Path | None:
    return (base / rel).resolve() if rel else None


def load_scenario(
    path: str | Path,
    *,
    population: list[str] | None = None,
    candidacy_seed_policy: str = "paper_originator_only",
) -> Scenario:
    path = Path(path).resolve()
    base = path.parent
    data = yaml.safe_load(path.read_text())
    agents_dir = _resolve(base, data.get("agents_dir", "agents"))
    assert agents_dir is not None
    ids: list[str] = list(data["agents"])
    if population:
        missing = [a for a in population if a not in ids]
        if missing:
            raise ValueError(f"population lists agents not in scenario {data['name']}: {missing}")
        ids = [a for a in ids if a in set(population)]
    events_path = _resolve(base, data.get("events"))
    events = (yaml.safe_load(events_path.read_text()) or {}).get("events", {}) if events_path and events_path.exists() else {}
    originators = {EVENT_FLAGS[k]: v.get("originator") for k, v in events.items() if k in EVENT_FLAGS}

    agents: dict[str, AgentSpec] = {}
    log: list[dict[str, Any]] = []
    for aid in ids:
        f = agents_dir / f"{aid}.yaml"
        raw_bytes = f.read_bytes()
        spec = yaml.safe_load(raw_bytes)
        identity = AgentIdentity(id=aid, **spec["identity"])
        seeds: list[SeedStatement] = []
        for i, s in enumerate(spec.get("seeds", [])):
            flags = list(s.get("flags", []))
            drop = None
            if candidacy_seed_policy == "paper_originator_only" and "candidacy_knowledge" in flags:
                origin = originators.get("candidacy_knowledge")
                if origin and origin != aid:
                    drop = "candidacy_knowledge held by a non-originator (paper p. 15)"
            if drop:
                log.append({"agent": aid, "seed_index": i, "text": s["text"], "action": "dropped", "reason": drop, "policy": candidacy_seed_policy})
                continue
            seeds.append(SeedStatement(i, s["text"], flags))
        for flag in spec.get("identity_flags", []):
            origin = originators.get(flag)
            if origin and origin != aid:
                log.append(
                    {"agent": aid, "field": "identity", "flag": flag, "action": "kept", "reason": "identity text is authored persona data; not rewritten"}
                )
        rc = dict(spec.get("released_code", {}))
        rc["_file_sha256"] = hashlib.sha256(raw_bytes).hexdigest()
        tile = spec.get("initial_tile")
        agents[aid] = AgentSpec(
            id=aid,
            identity=identity,
            perception=dict(spec.get("perception", {})),
            released_code=rc,
            initial_tile=tuple(tile) if tile else None,
            seeds=seeds,
            spatial_memory=spec.get("spatial_memory", {}) or {},
            identity_flags=list(spec.get("identity_flags", [])),
        )
    map_path = _resolve(base, data["map"])
    assert map_path is not None
    return Scenario(
        name=data["name"],
        path=path,
        description=str(data.get("description", "")).strip(),
        source=data.get("source", {}),
        start=datetime.fromisoformat(str(data.get("start", "2023-02-13T00:00:00"))),
        seconds_per_step=int(data.get("seconds_per_step", 10)),
        map_path=map_path,
        agent_ids=ids,
        agents=agents,
        events=events,
        events_path=events_path,
        constraints_path=_resolve(base, data.get("constraints")),
        candidacy_seed_policy=candidacy_seed_policy,
        seed_policy_log=log,
    )
