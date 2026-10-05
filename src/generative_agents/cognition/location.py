"""Choosing where an action happens (paper §5.1 pp. 12–13; spec J-2, J-6).

The agent walks down **its own** spatial memory (which may be stale or incomplete): area
(sector) → room (arena) → object, one prompt per level, with the paper's instruction to
prefer the current area. Choices are validated against the options shown and against the
real world tree; a level with a single known option is taken without a call (engineering).

Under ``constraints.policy = strict-v1`` a choice can be refused by the world (closed
store, someone else's room, occupied single-person bathroom). The refusal is stored in the
agent's memory as ``system_feedback``, the refused option is removed and the agent chooses
again (closed / private), or the caller makes the agent wait (occupied).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..providers.base import TaskFailed
from ..schemas import AgentIdentity, MemoryKind, MemoryOrigin
from ..world.constraints import ALLOW, Verdict
from ..world.hierarchy import WorldMap
from ..world.spatial import SpatialMemory
from .services import Services
from .summary import SummaryService

LEVELS = (("sector", "area", "areas"), ("arena", "room", "rooms"), ("object", "object", "objects"))


@dataclass
class LocationResult:
    address: str | None
    choices: list[dict[str, Any]] = field(default_factory=list)
    call_ids: list[int] = field(default_factory=list)
    rejections: list[dict[str, Any]] = field(default_factory=list)
    failure: str | None = None
    verdict: Verdict = ALLOW


def _canon(choice: str, options: list[str]) -> str | None:
    c = choice.strip().strip(".").strip('"').strip().lower()
    for o in options:
        if o.lower() == c:
            return o
    return None


class LocationChooser:
    def __init__(self, svc: Services, summary: SummaryService, world: WorldMap):
        self.svc = svc
        self.summary = summary
        self.world = world
        self.max_rechoices = 3

    def _options(self, spatial: SpatialMemory, prefix: list[str], exclude: set[str]) -> list[str]:
        w = self.world.world
        if len(prefix) == 0:
            names = spatial.sectors(w)
        elif len(prefix) == 1:
            names = spatial.arenas(w, prefix[0])
        else:
            names = spatial.objects(w, prefix[0], prefix[1])
        out = []
        for n in names:
            addr = ":".join([w, *prefix, n])
            if self.world.exists(addr) and addr not in exclude and self.world.walkable_tiles_for(addr):
                out.append(n)
        return out

    def _ask(
        self,
        identity: AgentIdentity,
        now: datetime,
        activity: str,
        level: tuple[str, str, str],
        options: list[str],
        here: tuple[str, str],
        spatial: SpatialMemory,
        chosen: list[str],
    ) -> tuple[str, list[int]]:
        w = self.world.world
        sector, arena = here
        if sector:
            current_place = f"{sector}: {arena}" if arena else sector
            kids = spatial.arenas(w, sector)
            current_children = f" that has {', '.join(kids)}" if kids and level[0] == "sector" else ""
        else:
            current_place, current_children = "the street", ""
        if level[0] != "sector":
            current_place = f"{current_place}, and is heading to {': '.join(chosen)}"
        home = identity.living_area.split(":")
        variables = {
            "agent_summary": self.summary.description(identity, now),
            "agent_name": identity.name,
            "current_place": current_place,
            "current_children": current_children,
            "level": level[1],
            "level_plural": level[2],
            "options": ", ".join(options),
            "activity": activity,
            "_options": options,
            "_activity": activity,
            "_home": home[1] if len(home) > 1 else "",
            "_room": home[2] if len(home) > 2 else "",
            "_current": (sector if level[0] == "sector" else arena if level[0] == "arena" else None),
        }
        out = self.svc.gateway.run(
            "choose_location",
            variables,
            agent_id=identity.id,
            sim_time=now,
            purpose=f"location:{level[0]}",
            validate=lambda o: [] if _canon(o.choice, options) else [f"choose exactly one of: {', '.join(options)}"],
        )
        return _canon(out.output.choice, options) or options[0], out.call_ids

    def choose(
        self,
        identity: AgentIdentity,
        activity: str,
        now: datetime,
        here: tuple[str, str],
        spatial: SpatialMemory,
        check: Callable[[str], Verdict] | None = None,
        exclude: set[str] | None = None,
    ) -> LocationResult:
        if self.svc.cfg.location.strategy == "single_call":
            return self.choose_single(identity, activity, now, here, spatial, check, exclude)
        res = LocationResult(None)
        excluded = set(exclude or ())
        w = self.world.world
        for _attempt in range(self.max_rechoices + 1):
            prefix: list[str] = []
            refused = False
            for level in LEVELS:
                options = self._options(spatial, prefix, excluded)
                if not options:
                    if level[0] == "object" and prefix:
                        break  # an arena without known objects is a valid destination
                    res.failure = f"no known {level[2]} to choose from" + (f" in {':'.join(prefix)}" if prefix else "")
                    return res
                if len(options) == 1:
                    pick = options[0]
                    res.choices.append({"level": level[0], "choice": pick, "options": options, "asked": False})
                else:
                    try:
                        pick, call_ids = self._ask(identity, now, activity, level, options, here, spatial, prefix)
                    except TaskFailed as exc:
                        res.call_ids += exc.call_ids
                        res.failure = f"{level[0]} choice failed: {exc}"
                        return res
                    res.call_ids += call_ids
                    res.choices.append({"level": level[0], "choice": pick, "options": options, "asked": True})
                prefix.append(pick)
                if level[0] in ("sector", "arena") and check is not None:
                    verdict = check(":".join([w, *prefix]))
                    if not verdict.allowed:
                        res.rejections.append({"address": ":".join([w, *prefix]), "rule": verdict.rule, "message": verdict.message})
                        self.feedback(identity, verdict, now)
                        if verdict.rule == "occupied":
                            res.verdict = verdict
                            res.address = ":".join([w, *prefix])
                            return res
                        excluded.add(":".join([w, *prefix]))
                        refused = True
                        break
            if not refused:
                res.address = ":".join([w, *prefix])
                return res
        res.failure = "every choice was refused by the world"
        return res

    def feedback(self, identity: AgentIdentity, verdict: Verdict, now: datetime) -> None:
        self.svc.remember(identity, verdict.message, MemoryKind.OBSERVATION, MemoryOrigin.SYSTEM_FEEDBACK, now, metadata={"rule": verdict.rule})
        self.svc.events.log("constraint", now, identity.id, rule=verdict.rule, message=verdict.message)

    def choose_single(
        self,
        identity: AgentIdentity,
        activity: str,
        now: datetime,
        here: tuple[str, str],
        spatial: SpatialMemory,
        check: Callable[[str], Verdict] | None = None,
        exclude: set[str] | None = None,
    ) -> LocationResult:
        """Engineering alternative (``location.strategy: single_call``): one prompt listing every
        known destination as "area: room: object" instead of three nested prompts."""

        res = LocationResult(None)
        excluded = set(exclude or ())
        w = self.world.world
        for _attempt in range(self.max_rechoices + 1):
            paths: dict[str, str] = {}
            for sector in self._options(spatial, [], excluded):
                for arena in self._options(spatial, [sector], excluded):
                    objs = self._options(spatial, [sector, arena], excluded)
                    for obj in objs or [""]:
                        label = ": ".join(x for x in (sector, arena, obj) if x)
                        paths[label] = ":".join(x for x in (w, sector, arena, obj) if x)
            if not paths:
                res.failure = "no known destination"
                return res
            options = sorted(paths)
            try:
                pick, call_ids = self._ask(identity, now, activity, ("place", "place (area: room: object)", "places"), options, here, spatial, [])
            except TaskFailed as exc:
                res.call_ids += exc.call_ids
                res.failure = f"place choice failed: {exc}"
                return res
            res.call_ids += call_ids
            res.choices.append({"level": "place", "choice": pick, "options": len(options), "asked": True})
            address = paths[pick]
            verdict = check(":".join(address.split(":")[:3])) if check is not None else ALLOW
            if verdict.allowed:
                res.address = address
                return res
            res.rejections.append({"address": address, "rule": verdict.rule, "message": verdict.message})
            self.feedback(identity, verdict, now)
            if verdict.rule == "occupied":
                res.verdict, res.address = verdict, ":".join(address.split(":")[:3])
                return res
            excluded.add(":".join(address.split(":")[:3]) if verdict.rule == "private" else ":".join(address.split(":")[:2]))
        res.failure = "every choice was refused by the world"
        return res
