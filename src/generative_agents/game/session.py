"""A live game session: the simulation in a background thread, steered by the interface.

The engine thread owns the simulation and its database connection. It steps the town at the
chosen speed, applies player actions at step boundaries (and while paused), and after every
step publishes an immutable snapshot (positions, actions, conversations, game state) that the
web server reads without touching the engine. Player actions go into ``actions.jsonl`` before
they take effect, tagged with the step they belong to, so a session can be resumed after a
crash and replayed exactly.

A replay session re-executes a recorded run (``Simulation(replay_from=...)``): every model
answer comes from the recording and every player action from its log. It makes no model call;
new player actions are refused because they would change what is being replayed.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any

from ..db import iso
from ..providers.base import BudgetExceeded, ProviderError, ReplayMiss
from ..schemas import PlanLevel, RunStatus
from ..simulation.engine import RunStopped, Simulation

SPEEDS = {"slow": 2.0, "normal": 6.0, "fast": 30.0, "max": 0.0}  # steps per real second (0 = as fast as possible)


class _ThinkingProbe:
    """Wraps the provider to show which resident is waiting for the model."""

    def __init__(self, inner: Any, session: GameSession):
        self.inner = inner
        self.session = session
        self.name = getattr(inner, "name", "provider")

    def describe(self) -> dict[str, Any]:
        return self.inner.describe()

    def complete(self, request: Any) -> Any:
        key = request.agent_id or "town"
        with self.session.lock:
            self.session._thinking[key] = {"task": request.task, "since": time.time()}
        try:
            return self.inner.complete(request)
        finally:
            with self.session.lock:
                self.session._thinking.pop(key, None)


class GameSession:
    def __init__(
        self,
        cfg: Any,
        run_dir: Path,
        *,
        replay_from: Path | None = None,
        provider: Any = None,
        embedding_provider: Any = None,
        speed: str = "normal",
        paused: bool = False,
        frame_buffer: int = 4000,
    ):
        if not cfg.game.enabled:
            raise ValueError("the config has game.enabled: false")
        self.cfg = cfg
        self.run_dir = Path(run_dir)
        self.replay = replay_from is not None
        self.sim = Simulation(cfg, self.run_dir, replay_from=replay_from, provider=provider, embedding_provider=embedding_provider)
        self.game = self.sim.game
        self.sim.rt.gateway.provider = _ThinkingProbe(self.sim.rt.gateway.provider, self)
        self.end: datetime = cfg.scenario.end
        if replay_from is not None:
            source = json.loads((Path(replay_from) / "manifest.json").read_text())
            self.end = min(self.end, self.sim.clock.time_at(int(source.get("next_step", 0))))
        self.lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="game-engine", daemon=True)
        self.paused = paused
        self.speed = speed if speed in SPEEDS else "normal"
        self.status = "starting"
        self.error: str | None = None
        self._in_step = False
        self._ready = False
        self.epoch = 0  # bumps when a failure rolls the town back to its last checkpoint
        self._thinking: dict[str, dict[str, Any]] = {}
        self._frames: deque[dict[str, Any]] = deque(maxlen=frame_buffer)
        self._feed: deque[dict[str, Any]] = deque(maxlen=frame_buffer)
        self._feed_seq = 0
        self._published: dict[str, Any] = {}
        self._conv_cursor = 0
        self._last_schedules_step = -999
        self._schedules: dict[str, Any] = {}
        self._objects: dict[str, Any] = {}
        self.game.listeners.append(self._on_game_event)

    # ================================================================== lifecycle
    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 30.0) -> None:
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout)

    def _run(self) -> None:
        sim = self.sim
        try:
            while not self._stop.is_set():
                if not self._ready:
                    if self.error:  # wait for Retry
                        self._wake.wait(0.5)
                        self._wake.clear()
                        continue
                    try:
                        self._set_status("initializing" if not sim.initialized() else "starting")
                        sim.begin()
                    except RunStopped as stop:
                        self._failed(stop.status.value, stop.detail)
                        continue
                    self._ready = True
                    self.game.ensure_started(sim.clock.now)
                    self._publish(frame=True)
                    continue
                if self.paused or self.finished or self.error:
                    with self.lock:  # only the engine thread reports that stepping has stopped
                        if not self.error:
                            self.status = "finished" if self.finished else "paused"
                    self._service_actions()
                    self._wake.wait(0.2)
                    self._wake.clear()
                    continue
                started = time.monotonic()
                with self.lock:
                    self._in_step = True
                    self.status = "running"
                try:
                    sim.advance()
                except RunStopped as stop:
                    sim._abort(stop.status, stop.detail)
                    self._failed(stop.status.value, stop.detail)
                    continue
                finally:
                    with self.lock:
                        self._in_step = False
                self._publish(frame=True)
                if self.finished:
                    self._set_status("finished")
                    self.paused = True
                rate = SPEEDS[self.speed]
                if rate > 0:
                    left = 1.0 / rate - (time.monotonic() - started)
                    if left > 0:
                        self._wake.wait(left)
                        self._wake.clear()
            if self._ready and not self.error:
                sim.finish(sim.wind_down())
            else:
                sim.write_manifest()
        except Exception as exc:  # pragma: no cover - shown to the player, never swallowed
            self._failed("error", f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=3)}")
        finally:
            sim.close()

    @property
    def finished(self) -> bool:
        return self.sim.clock.now >= self.end

    def _failed(self, status: str, detail: str) -> None:
        with self.lock:
            self.error = detail
            self.status = status
            self._ready = False
            self.epoch += 1
            self._frames.clear()
            self._feed_seq += 1
            self._feed.append({"seq": self._feed_seq, "kind": "stopped", "status": status, "detail": detail})

    def _set_status(self, status: str) -> None:
        with self.lock:
            self.status = status

    def _service_actions(self) -> None:
        """While paused, apply actions logged for the current step boundary."""

        sim = self.sim
        if self.replay or self.error or not self._ready:
            return
        due = self.game.actions.due(sim.clock.step, int(self.game.store.get("applied_seq")))
        if not due:
            return
        try:
            self.game.apply_due(sim.clock.now)
            self.game.store.flush()
        except (BudgetExceeded, ProviderError, ReplayMiss) as exc:
            status = RunStatus.BUDGET_EXHAUSTED if isinstance(exc, BudgetExceeded) else RunStatus.PROVIDER_FAILURE
            sim._abort(status, str(exc))
            self._failed(status.value, str(exc))
            return
        self._publish(frame=False)

    # ================================================================== player input
    def submit(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Log an action for the next step boundary. Raises ``PermissionError`` in a replay."""

        if self.replay:
            raise PermissionError("this is a replay: it only shows what was recorded")
        if self.error:
            raise PermissionError("the town stopped: " + self.error.splitlines()[0])
        with self.lock:
            step = self.sim.clock.step + (1 if self._in_step else 0)
            act = self.game.actions.append(step, kind, payload)
        self._wake.set()
        return {"seq": act.seq, "step": act.step}

    def control(self, action: str, speed: str | None = None) -> dict[str, Any]:
        with self.lock:
            if action == "pause":
                self.paused = True
            elif action == "resume":
                if self.finished:
                    raise PermissionError("the scenario has reached its end time")
                self.paused = False
            elif action == "speed":
                if speed not in SPEEDS:
                    raise ValueError(f"speed must be one of {', '.join(SPEEDS)}")
                self.speed = speed
            elif action == "retry":
                if not self.error:
                    raise ValueError("nothing to retry")
                if self.replay:
                    raise PermissionError("a replay that stopped cannot continue")
                self.error = None
                self.status = "starting"
            else:
                raise ValueError("action must be pause, resume, speed or retry")
        self._wake.set()
        return {"paused": self.paused, "speed": self.speed, "status": self.status}

    def validate_build(self, ops: list[dict[str, Any]]) -> dict[str, Any]:
        with self.lock:
            snap = self._published.get("build_snapshot")
        if snap is None:
            return {"ok": False, "problems": ["the town is still waking up"], "verdicts": [], "cost": {}, "refund": {}, "feedback": []}
        return self.game.validate_build(ops, snapshot=snap)

    # ================================================================== publishing (engine thread)
    def _on_game_event(self, ev: dict[str, Any]) -> None:
        with self.lock:
            self._feed_seq += 1
            self._feed.append({"seq": self._feed_seq, **ev})

    def _frame_now(self) -> dict[str, Any]:
        sim = self.sim
        agents = {}
        for aid in sim.order:
            st = sim.svc.states.get(aid)
            v = sim.view_of(aid)
            a = st.action
            agents[aid] = {
                "x": int(st.tile[0]) if st.tile else None,
                "y": int(st.tile[1]) if st.tile else None,
                "activity": v.activity,
                "kind": a.kind,
                "address": a.address,
                "sleeping": v.sleeping,
                "conversation": a.conversation_id if a.kind == "conversation" else None,
                "partner": v.conversation_partner,
                "path_left": len(a.path or []),
            }
        return {"step": sim.clock.step - 1, "time": iso(sim.clock.time_at(max(0, sim.clock.step - 1))), "agents": agents}

    def _new_conversations(self) -> list[dict[str, Any]]:
        out = []
        for row in self.sim.db.query("SELECT id, json FROM conversations ORDER BY id"):
            num = int(row["id"].lstrip("c") or 0)
            if num <= self._conv_cursor:
                continue
            self._conv_cursor = num
            conv = json.loads(row["json"])
            out.append(
                {
                    "kind": "conversation",
                    "conversation_id": row["id"],
                    "participants": conv.get("participants"),
                    "started_at": conv.get("started_at"),
                    "ended_at": conv.get("ended_at"),
                    "location": conv.get("location"),
                    "status": conv.get("status"),
                    "summary": conv.get("summary"),
                    "lines": [{"speaker": u.get("speaker_id"), "text": u.get("text")} for u in conv.get("utterances", [])],
                }
            )
        return out

    def _schedules_now(self) -> dict[str, Any]:
        sim = self.sim
        now = sim.clock.now
        day = now.date().isoformat()
        out = {}
        for aid in sim.order:
            blocks = sim.plans.items(aid, day=day, level=PlanLevel.HOUR)
            task = sim.plans.at(aid, PlanLevel.TASK, now)
            out[aid] = {
                "day": day,
                "blocks": [{"start": iso(b.start), "minutes": b.duration_min, "description": b.description} for b in blocks],
                "task": {"start": iso(task.start), "minutes": task.duration_min, "description": task.description} if task else None,
            }
        return out

    def _publish(self, frame: bool) -> None:
        sim, game = self.sim, self.game
        now = sim.clock.now
        frame_data = self._frame_now() if frame else None
        convs = self._new_conversations()
        if sim.clock.step - self._last_schedules_step >= 6 or not self._schedules:
            self._schedules = self._schedules_now()
            self._objects = sim.world_state.to_json()["objects"]
            self._last_schedules_step = sim.clock.step
        state = game.state(now)
        snap = game.build_snapshot()
        totals = sim.rt.ledger.totals()
        with self.lock:
            if frame_data is not None:
                self._frames.append(frame_data)
            for c in convs:
                self._feed_seq += 1
                self._feed.append({"seq": self._feed_seq, **c})
            self._published = {
                "clock": {"step": sim.clock.step, "time": iso(now), "end": iso(self.end)},
                "game": state,
                "schedules": self._schedules,
                "objects": self._objects,
                "build_snapshot": snap,
                "ledger": {
                    "calls": int(totals.get("calls") or 0),
                    "input_tokens": int(totals.get("input_tokens") or 0),
                    "output_tokens": int(totals.get("output_tokens") or 0),
                },
                "budget": sim.rt.budget.snapshot(),
            }

    # ================================================================== reading (web thread)
    def poll(self, since_step: int = -2, since_feed: int = 0) -> dict[str, Any]:
        with self.lock:
            pub = self._published
            frames = [f for f in self._frames if f["step"] > since_step]
            if len(frames) > 600:
                frames = frames[-600:]
            feed = [e for e in self._feed if e["seq"] > since_feed]
            return {
                "epoch": self.epoch,
                "status": self.status,
                "paused": self.paused,
                "speed": self.speed,
                "replay": self.replay,
                "error": self.error,
                "thinking": {k: dict(v) for k, v in self._thinking.items()},
                "clock": pub.get("clock"),
                "frames": frames,
                "feed": feed,
                "feed_seq": self._feed_seq,
                "game": pub.get("game"),
                "schedules": pub.get("schedules"),
                "objects": pub.get("objects"),
                "ledger": pub.get("ledger"),
            }
