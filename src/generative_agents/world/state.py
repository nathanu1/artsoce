"""Authoritative world state: object states and ambient events (paper §5.1; spec J-5, L-2).

Agent positions and actions live in each agent's ``AgentState``; this module keeps what
belongs to the world itself.

Object states follow the released convention: every object is ``idle`` unless something
sets it. Three sources are distinguished:

* ``agent``: the state an agent's current action puts the object in (e.g. "being slept in").
  It overlays the object only while that agent uses it; when the agent leaves, the object
  shows its lasting state again. The released code achieves the same by resetting object
  events at the start of every cycle (reverie.py:326-332).
* ``lasting``: a condition that outlives the action, either written by a researcher
  intervention (e.g. a stove "burning", a refrigerator "empty") or left behind by an action
  whose grounding reported a lasting change (e.g. the stove "turned off").
* ``default``: ``idle``.

Ambient events are things visible at a tile that are not objects (e.g. a street fire). They
are perceived like object events, by agents in the same arena within vision.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from ..db import Database

IDLE = "idle"


class ObjectState(BaseModel):
    lasting: str = IDLE
    lasting_source: str = "default"  # default | intervention | agent
    lasting_since: datetime | None = None
    in_use: str | None = None  # overlay while an agent uses the object
    in_use_by: str | None = None
    in_use_since: datetime | None = None

    @property
    def state(self) -> str:
        return self.in_use if self.in_use and self.in_use != IDLE else self.lasting

    def is_default(self) -> bool:
        return self.lasting == IDLE and self.lasting_source == "default" and not self.in_use_by


class AmbientEvent(BaseModel):
    id: str
    tile: tuple[int, int]
    subject: str
    predicate: str = "is"
    object: str = ""
    description: str
    started_at: datetime
    until: datetime | None = None
    note: str | None = None

    def active(self, now: datetime) -> bool:
        return self.started_at <= now and (self.until is None or now < self.until)


class WorldState:
    def __init__(self, db: Database):
        self.db = db
        self.objects: dict[str, ObjectState] = {}
        self.ambient: dict[str, AmbientEvent] = {}
        self._dirty: set[str] = set()
        self.load()

    # ------------------------------------------------------------------ persistence
    def load(self) -> None:
        self.objects.clear()
        self.ambient.clear()
        self._dirty.clear()
        for row in self.db.query("SELECT address, json FROM world_objects"):
            if row["address"].startswith("ambient:"):
                ev = AmbientEvent.model_validate_json(row["json"])
                self.ambient[ev.id] = ev
            else:
                self.objects[row["address"]] = ObjectState.model_validate_json(row["json"])

    invalidate = load

    def flush(self) -> None:
        for key in sorted(self._dirty):
            if key.startswith("ambient:"):
                ev = self.ambient.get(key[len("ambient:") :])
                if ev is None:
                    self.db.execute("DELETE FROM world_objects WHERE address=?", (key,))
                else:
                    self._upsert(key, ev.model_dump_json())
                continue
            st = self.objects.get(key)
            if st is None or st.is_default():
                self.objects.pop(key, None)
                self.db.execute("DELETE FROM world_objects WHERE address=?", (key,))
            else:
                self._upsert(key, st.model_dump_json())
        self._dirty.clear()

    def _upsert(self, key: str, payload: str) -> None:
        self.db.execute(
            "INSERT INTO world_objects(address, json) VALUES(?, ?) ON CONFLICT(address) DO UPDATE SET json=excluded.json",
            (key, payload),
        )

    # ------------------------------------------------------------------ objects
    def get(self, address: str) -> ObjectState:
        return self.objects.get(address) or ObjectState()

    def state_of(self, address: str) -> str:
        st = self.objects.get(address)
        return st.state if st else IDLE

    def _mut(self, address: str) -> ObjectState:
        st = self.objects.get(address)
        if st is None:
            st = self.objects[address] = ObjectState()
        self._dirty.add(address)
        return st

    def use(self, address: str, agent_id: str, state: str | None, now: datetime) -> None:
        """An agent's action puts the object in ``state`` while the agent is there."""

        st = self._mut(address)
        st.in_use = state or IDLE
        st.in_use_by = agent_id
        st.in_use_since = now

    def set_lasting(self, address: str, state: str, now: datetime, source: str) -> None:
        st = self._mut(address)
        st.lasting = state or IDLE
        st.lasting_source = source if state and state != IDLE else "default"
        st.lasting_since = now

    def release(self, agent_id: str, keep: str | None = None) -> list[str]:
        """Drop the agent's in-use overlays (except on ``keep``); returns affected addresses."""

        out = []
        for address, st in self.objects.items():
            if st.in_use_by == agent_id and address != keep:
                st.in_use = None
                st.in_use_by = None
                st.in_use_since = None
                self._dirty.add(address)
                out.append(address)
        return out

    def forget(self, address: str) -> None:
        """The object no longer exists (a placed item was removed or renamed)."""

        self.objects.pop(address, None)
        self._dirty.add(address)

    def user_of(self, address: str) -> str | None:
        st = self.objects.get(address)
        return st.in_use_by if st else None

    # ------------------------------------------------------------------ ambient events
    def add_ambient(self, event: AmbientEvent) -> None:
        self.ambient[event.id] = event
        self._dirty.add(f"ambient:{event.id}")

    def end_ambient(self, event_id: str, now: datetime) -> None:
        ev = self.ambient.get(event_id)
        if ev is not None:
            ev.until = now
            self._dirty.add(f"ambient:{event_id}")

    def active_ambient(self, now: datetime) -> list[AmbientEvent]:
        return sorted((e for e in self.ambient.values() if e.active(now)), key=lambda e: e.id)

    def to_json(self) -> dict[str, Any]:
        return {
            "objects": {a: json.loads(s.model_dump_json()) for a, s in sorted(self.objects.items()) if not s.is_default()},
            "ambient": {i: json.loads(e.model_dump_json()) for i, e in sorted(self.ambient.items())},
        }
