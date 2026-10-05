"""The player's action log (``actions.jsonl``): the game's only input besides the model.

Every player action is appended here, with the simulation step it belongs to, before the
engine applies it. A resume re-applies logged actions whose effects were rolled back, and a
replay applies the source run's log at the same steps; together with the call ledger that
reproduces a played run exactly, without calling a model.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

KINDS = {
    "chat",  # {agent, text}
    "gift",  # {agent, gift}
    "ask_request",  # {agent}
    "deliver",  # {request}
    "search",  # {address}
    "collect_sparkle",  # {sparkle}
    "build",  # {ops: [...]}
    "save_template",  # {name, parts}
    "object_state",  # {address, state}   (the paper's object-state edit)
    "whisper",  # {agent, text}       (the paper's inner voice)
}


@dataclass
class Action:
    seq: int
    step: int
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    wall: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {"seq": self.seq, "step": self.step, "kind": self.kind, "payload": self.payload, "wall": self.wall}


class ActionLog:
    def __init__(self, path: str | Path, *, readonly: bool = False):
        self.path = Path(path)
        self.readonly = readonly
        self._lock = threading.Lock()
        self.items: list[Action] = []
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    d = json.loads(line)
                    self.items.append(Action(int(d["seq"]), int(d["step"]), d["kind"], d.get("payload") or {}, float(d.get("wall") or 0.0)))

    def append(self, step: int, kind: str, payload: dict[str, Any]) -> Action:
        if self.readonly:
            raise RuntimeError("this action log is read-only (replay)")
        if kind not in KINDS:
            raise ValueError(f"unknown action kind {kind!r}")
        with self._lock:
            act = Action(seq=(self.items[-1].seq + 1) if self.items else 1, step=int(step), kind=kind, payload=dict(payload), wall=time.time())
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(act.to_json(), sort_keys=True) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            self.items.append(act)
            return act

    def due(self, step: int, after_seq: int) -> list[Action]:
        """Unapplied actions for ``step`` or earlier, in the order they were made."""

        with self._lock:
            return [a for a in self.items if a.seq > after_seq and a.step <= step]

    def __len__(self) -> int:
        return len(self.items)
