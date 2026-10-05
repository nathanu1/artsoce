"""World constraints, enforced only under ``constraints.policy = strict-v1`` (spec J-7).

The paper reports agents entering closed stores, occupied single-person bathrooms and other
people's rooms (p. 17) and did not enforce any norms. ``strict-v1`` is an engineering
adaptation that applies the same rules to every condition:

* ``closed``: a sector with opening hours can be entered only while open (staff exempt);
* ``occupied``: an arena matching a single-occupancy pattern holds one agent at a time
  (agents already inside, plus agents already heading there, count);
* ``private``: an arena named after people ("Klaus Mueller's room", "Mei and John Lin's
  bedroom") is entered only by the people it names.

A rejected move is never silently rewritten: the caller stores the rejection as a
``system_feedback`` memory for the agent, logs it, and lets the agent choose again or wait.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ..schemas import AgentIdentity


def clock_minutes(text: str) -> int:
    """'08:00' -> 480; '24:00' -> 1440."""

    h, m = text.strip().split(":")
    return int(h) * 60 + int(m)


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    rule: str | None = None  # closed | occupied | private
    message: str = ""
    retry_after_min: int | None = None


ALLOW = Verdict(True)


@dataclass
class Constraints:
    policy: str = "none"
    opening_hours: dict[str, dict[str, Any]] = field(default_factory=dict)
    single_occupancy: list[str] = field(default_factory=list)
    private_patterns: list[str] = field(default_factory=list)
    wait_minutes: int = 5

    @classmethod
    def load(cls, path: str | Path | None, policy: str) -> Constraints:
        if policy == "none" or not path:
            return cls(policy="none")
        data = yaml.safe_load(Path(path).read_text()) or {}
        return cls(
            policy=policy,
            opening_hours=data.get("opening_hours", {}) or {},
            single_occupancy=list(data.get("single_occupancy_arena_patterns", []) or []),
            private_patterns=list(data.get("private_room_patterns", []) or []),
        )

    @property
    def active(self) -> bool:
        return self.policy != "none"

    # ------------------------------------------------------------------ rules
    def hours_for(self, sector_address: str) -> dict[str, Any] | None:
        return self.opening_hours.get(sector_address)

    def is_open(self, sector_address: str, now: datetime) -> bool:
        h = self.hours_for(sector_address)
        if not h:
            return True
        minute = now.hour * 60 + now.minute
        return clock_minutes(h["open"]) <= minute < clock_minutes(h["close"])

    def is_single_occupancy(self, arena_address: str) -> bool:
        name = arena_address.split(":")[-1]
        return any(re.search(p, name, re.I) for p in self.single_occupancy)

    def private_owners(self, arena_address: str) -> str | None:
        """The owner phrase of a private room ("Mei and John Lin"), or None if not private."""

        name = arena_address.split(":")[-1]
        for p in self.private_patterns:
            if re.search(p, name, re.I):
                owners = name.rsplit("'s ", 1)[0] if "'s " in name else name
                # only rooms named after people ("Klaus Mueller's room"), not "man's bathroom"
                return owners if re.search(r"\b[A-Z][a-z]+\b", owners) else None
        return None

    @staticmethod
    def names_person(owner_phrase: str, identity: AgentIdentity) -> bool:
        words = set(re.findall(r"[a-z]+", owner_phrase.lower()))
        return identity.first_name.lower() in words and identity.last_name.lower() in words

    def check(
        self,
        identity: AgentIdentity,
        address: str,
        now: datetime,
        occupants: dict[str, set[str]] | None = None,
        current_arena: str | None = None,
    ) -> Verdict:
        """May ``identity`` go to ``address`` (any level) now?"""

        if not self.active or not address:
            return ALLOW
        parts = address.split(":")
        sector = ":".join(parts[:2]) if len(parts) >= 2 else None
        arena = ":".join(parts[:3]) if len(parts) >= 3 else None
        if sector:
            h = self.hours_for(sector)
            if h and identity.id not in (h.get("staff") or []) and not self.is_open(sector, now):
                place = parts[1]
                return Verdict(False, "closed", f"{place} is closed right now; it is open from {h['open']} to {h['close']}.")
        if arena:
            owners = self.private_owners(arena)
            if owners is not None and not self.names_person(owners, identity):
                return Verdict(False, "private", f"{parts[2]} is {owners}'s private room; {identity.first_name} cannot go in.")
            if self.is_single_occupancy(arena) and arena != current_arena:
                others = sorted((occupants or {}).get(arena, set()) - {identity.id})
                if others:
                    return Verdict(
                        False,
                        "occupied",
                        f"The {parts[2]} at {parts[1]} is occupied right now.",
                        retry_after_min=self.wait_minutes,
                    )
        return ALLOW

    def describe(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "opening_hours": self.opening_hours,
            "single_occupancy_patterns": self.single_occupancy,
            "private_room_patterns": self.private_patterns,
        }
