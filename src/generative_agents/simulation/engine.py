"""The simulation loop (paper §5; spec K-1 … K-6, L-1 … L-3).

One step is ``seconds_per_step`` of simulated time (10 s in the reference run):

1. **Snapshot.** Every agent's tile and visible action are frozen; all perception in this
   step reads the snapshot, so the update order cannot leak one agent's decision into
   another agent's observations.
2. **Per agent, in a fixed order:** plan the day if needed, perceive, store new
   observations (retention dedupe), reflect if triggered, follow the current plan task
   (location → path → action grounding), and consider one focal percept for a reaction.
   A "talk" decision is recorded as a request.
3. **Conversations** are resolved in the same fixed order; an agent takes part in at most
   one conversation per step.
4. **Commit.** Agents advance one tile along their paths; objects show the state of the
   action using them; frames and events are written. Every ``checkpoint_every_steps`` the
   state database is committed together with the clock and budget.

If a provider call fails for good, or a budget ceiling is crossed, the open step is rolled
back to the last checkpoint and the run stops with a status that says why. Calls already
made stay in the provider ledger, so resuming re-uses them instead of paying again.
"""

from __future__ import annotations

import json
import platform
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from .. import __version__
from ..cognition.dialogue import DialogueEngine, Side
from ..cognition.location import LocationChooser, LocationResult
from ..cognition.planning import Planner, PlanStore, is_sleep
from ..cognition.reaction import ReactionEngine, focal_percept
from ..cognition.reflection import ReflectionEngine
from ..cognition.summary import SummaryService
from ..config import GAConfig, repo_path
from ..db import Database, iso, parse_iso, stable_json
from ..memory.seeds import seed_agent
from ..providers.base import BudgetExceeded, ProviderError, ReplayMiss, TaskFailed
from ..scenario.loader import Scenario, load_scenario
from ..schemas import ActionState, AgentIdentity, MemoryKind, MemoryOrigin, PlanItem, RunStatus
from ..world.constraints import ALLOW, Constraints, Verdict
from ..world.navigation import Navigator
from ..world.perception import AgentView, Perceiver, Percept
from ..world.spatial import SpatialMemory, SpatialStore
from ..world.state import IDLE, AmbientEvent, WorldState
from .clock import SimClock, long_time
from .runtime import Runtime, build_runtime, make_services

Tile = tuple[int, int]


class ReplayOnlyLLM:
    """Stands in for the model during a replay; the gateway answers from the ledger first."""

    name = "replay"

    def describe(self) -> dict[str, Any]:
        return {"provider": "replay", "fresh_calls": False}

    def complete(self, request: Any) -> Any:  # pragma: no cover - the gateway raises ReplayMiss first
        raise ReplayMiss(f"replay would need a fresh call for {request.task}")


class ReplayOnlyEmbedding:
    """Carries the source run's embedding identity; refuses to embed anything new."""

    is_fixture = False

    def __init__(self, model: str | None, revision: str | None, dims: int | None):
        self.model_id = model or "unknown"
        self.revision = revision
        self.dims = int(dims or 0)

    def describe(self) -> dict[str, Any]:
        return {"kind": "replay", "model": self.model_id, "revision": self.revision, "dims": self.dims, "fixture": False}

    def embed(self, texts: list[str]) -> Any:
        raise ReplayMiss(f"replay needs {len(texts)} embedding(s) that the source run did not store")


class RunStopped(Exception):
    """Raised inside a step to stop the run cleanly (budget, provider failure)."""

    def __init__(self, status: RunStatus, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass
class TalkRequest:
    initiator: str
    partner: str
    percept: Percept
    reason: str


@dataclass
class StepReport:
    step: int
    sim_time: datetime
    new_memories: int = 0
    reflections: int = 0
    conversations: list[str] = field(default_factory=list)
    actions_started: int = 0


def git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path("."), capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except Exception:  # pragma: no cover - git missing
        return None


class Simulation:
    def __init__(
        self,
        cfg: GAConfig,
        run_dir: str | Path,
        *,
        scenario: Scenario | None = None,
        provider: Any = None,
        embedding_provider: Any = None,
        replay_from: str | Path | None = None,
        db_path: str | Path | None = None,
    ):
        """``replay_from``: a finished run directory to re-execute from its provider ledger.

        A replay uses the source run's own configuration, answers every model request from
        the source ledger (a request that is not there stops the replay as diverged) and
        reads embeddings from the source run's database. It never calls a model.
        """

        self.cfg = cfg
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = self.run_dir.name
        self.scenario = scenario or load_scenario(
            repo_path(cfg.scenario.path), population=cfg.scenario.population, candidacy_seed_policy=cfg.scenario.candidacy_seed_policy
        )
        self.world = self.scenario.world
        self.db = Database(db_path or self.run_dir / "state.sqlite")
        start = cfg.scenario.start
        self.clock = SimClock(start, cfg.scenario.seconds_per_step, int(self.db.get_meta("next_step", 0)))
        self.replay_from = Path(replay_from) if replay_from else None
        self.replay_scope: str | None = None
        self._initializing = False
        ledger_path = self.run_dir / "provider.sqlite"
        if self.replay_from is not None:
            source = json.loads((self.replay_from / "manifest.json").read_text())
            self.replay_scope = source["run_id"]
            ledger_path = self.replay_from / "provider.sqlite"
            provider = provider or ReplayOnlyLLM()
            emb = source.get("embeddings", {})
            embedding_provider = embedding_provider or ReplayOnlyEmbedding(emb.get("model"), emb.get("revision"), emb.get("dims"))
            self._import_embeddings(self.replay_from / "state.sqlite")
        self.rt: Runtime = build_runtime(
            cfg,
            store=None,
            ledger_path=ledger_path,
            scope=self.run_id,
            step_getter=self.ledger_step,
            replay_scope=self.replay_scope,
            provider=provider,
            embedding_provider=embedding_provider,
        )
        from ..memory.store import MemoryStore

        store = MemoryStore(self.db)
        self.rt.embeddings.store = store
        self.identities: dict[str, AgentIdentity] = self.scenario.identities()
        self.order = list(self.scenario.agent_ids)
        self.svc = make_services(cfg, self.db, self.rt, self.identities, step_getter=self.ledger_step)
        self.summary = SummaryService(self.svc)
        self.plans = PlanStore(self.db)
        self.planner = Planner(self.svc, self.summary, self.plans)
        self.reflection = ReflectionEngine(self.svc)
        self.locations = LocationChooser(self.svc, self.summary, self.world)
        self.reaction = ReactionEngine(self.svc, self.summary)
        self.dialogue = DialogueEngine(self.svc, self.summary, self.reaction)
        self.spatial = SpatialStore(self.db)
        self.world_state = WorldState(self.db)
        self.nav = Navigator(self.world)
        self.perceiver = Perceiver(self.world)
        cpath = self.scenario.constraints_path
        self.constraints = Constraints.load(cpath, cfg.constraints.policy)
        self.interventions: list[dict[str, Any]] = list(self._load_interventions())
        self.on_step: list[Callable[[StepReport], None]] = []
        # Extension hooks (the game layer): inside a step's error handling, before the agents
        # act and after moves are committed; flush and invalidate follow the engine's own state.
        self.before_step_hooks: list[Callable[[datetime], None]] = []
        self.after_step_hooks: list[Callable[[datetime], None]] = []
        self.flush_hooks: list[Callable[[], None]] = []
        self.invalidate_hooks: list[Callable[[], None]] = []
        self._last_frame: dict[str, list[Any]] = {}
        self._talk_requests: list[TalkRequest] = []
        self._busy: set[str] = set()
        self._report: StepReport | None = None
        self.game: Any = None
        if cfg.game.enabled:
            from ..game.layer import GameLayer

            self.db.execute("PRAGMA journal_mode=WAL")  # the live game reads while the engine writes
            source = self.replay_from if self.replay_from is not None else self.run_dir
            self.game = GameLayer(self, actions_path=source / "actions.jsonl", readonly_actions=self.replay_from is not None)

    def _import_embeddings(self, source_db: Path) -> None:
        if self.db.get_meta("embeddings_imported"):
            return
        self.db.execute("ATTACH DATABASE ? AS src", (str(source_db),))
        self.db.execute("INSERT OR IGNORE INTO embeddings SELECT * FROM src.embeddings")
        self.db.commit()
        self.db.execute("DETACH DATABASE src")
        self.db.set_meta("embeddings_imported", True)
        self.db.commit()

    # ================================================================== lifecycle
    def ledger_step(self) -> int:
        """Step recorded with each call and event; initialization is step -1."""

        return -1 if self._initializing else self.clock.step

    @property
    def status(self) -> str:
        return str(self.db.get_meta("status", RunStatus.CREATED.value))

    def initialized(self) -> bool:
        return bool(self.db.get_meta("initialized", False))

    def initialize(self) -> None:
        """Create agents, seed memories and spatial memory (step 0). Idempotent per run."""

        if self.initialized():
            raise RuntimeError(f"run {self.run_id} is already initialized")
        now = self.clock.now
        sc = self.scenario
        self._initializing = True
        try:
            for idx, aid in enumerate(self.order):
                spec = sc.agents[aid]
                self.db.execute(
                    "INSERT INTO agents(id, name, order_index, identity_json) VALUES(?,?,?,?)",
                    (aid, spec.identity.name, idx, spec.identity.model_dump_json()),
                )
                state = self.svc.states.get(aid)
                state.tile = self._spawn_tile(spec)
                state.extra["perception"] = self._perception(spec)
                self.reflection.init_state(aid)
                mem = SpatialMemory(aid, spec.spatial_memory)
                self.spatial.put(mem)
                seed_agent(self.svc, spec, now, self.cfg.scenario.seed_rendering)
            self.db.set_meta("initialized", True)
            self.db.set_meta("run_id", self.run_id)
            self.db.set_meta("mode", self.cfg.run_mode)
            self.db.set_meta("scenario", sc.manifest())
            self.db.set_meta("status", RunStatus.CREATED.value)
            self._checkpoint(note="initialized")
            if "initial" in self.cfg.output.snapshots:
                self.snapshot("initial")
        except (BudgetExceeded, ProviderError, ReplayMiss) as exc:
            self.db.rollback()
            self._invalidate()
            raise RunStopped(RunStatus.BUDGET_EXHAUSTED if isinstance(exc, BudgetExceeded) else RunStatus.PROVIDER_FAILURE, str(exc)) from exc
        finally:
            self._initializing = False
        self.write_manifest()

    def _perception(self, spec: Any) -> dict[str, int]:
        p = dict(spec.perception)
        for k in ("vision_r", "att_bandwidth", "retention"):
            v = getattr(self.cfg.perception, k)
            if v is not None:
                p[k] = v
        return {"vision_r": int(p.get("vision_r", 8)), "att_bandwidth": int(p.get("att_bandwidth", 8)), "retention": int(p.get("retention", 8))}

    def _spawn_tile(self, spec: Any) -> Tile:
        if spec.initial_tile and self.nav.walkable(tuple(spec.initial_tile)):
            return (int(spec.initial_tile[0]), int(spec.initial_tile[1]))
        tiles = self.world.walkable_tiles_for(spec.identity.living_area) or self.world.walkable_tiles_for(":".join(spec.identity.living_area.split(":")[:2]))
        if not tiles:
            raise ValueError(f"no walkable spawn tile for {spec.id}")
        return min(tiles, key=lambda t: (t[1], t[0]))

    def _load_interventions(self) -> list[dict[str, Any]]:
        path = self.run_dir / "interventions.yaml"
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        items = data.get("interventions", data if isinstance(data, list) else [])
        out = []
        for i, it in enumerate(items):
            it = dict(it)
            it["_index"] = i
            it["at"] = datetime.fromisoformat(str(it["at"]))
            out.append(it)
        return sorted(out, key=lambda x: (x["at"], x["_index"]))

    def schedule_intervention(self, item: dict[str, Any]) -> None:
        """Append an intervention to the run's interventions.yaml (researcher tool)."""

        path = self.run_dir / "interventions.yaml"
        data = yaml.safe_load(path.read_text()) if path.exists() else None
        items = (data or {}).get("interventions", []) if isinstance(data, dict) or data is None else data
        clean = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in item.items() if not k.startswith("_")}
        items.append(clean)
        path.write_text(yaml.safe_dump({"interventions": items}, sort_keys=False, allow_unicode=True))
        self.interventions = self._load_interventions()

    # ================================================================== stepping
    def run(self, *, until: datetime | None = None, max_steps: int | None = None, progress: Callable[[int, datetime], None] | None = None) -> str:
        """Run until ``until`` (default: scenario end) or ``max_steps``; returns the final status."""

        end = until or self.cfg.scenario.end
        steps = 0
        status = RunStatus.RUNNING
        try:
            self.begin()
            while self.clock.now < end and (max_steps is None or steps < max_steps):
                self.advance()
                steps += 1
                if progress is not None:
                    progress(self.clock.step, self.clock.now)
            status = self.wind_down()
        except RunStopped as stop:
            status = stop.status
            self._abort(stop.status, stop.detail)
        except KeyboardInterrupt:
            status = RunStatus.INTERRUPTED
            self._abort(status, "interrupted by user")
        return self.finish(status)

    # The three pieces of ``run``, also used by the live game session to step one at a time.
    def begin(self) -> None:
        """Initialize if needed and prepare to step (resume-safe). May raise ``RunStopped``."""

        if not self.initialized():
            self.initialize()
        self.check_scenario_unchanged()
        self.rt.budget.restore(self.db.get_meta("budget"))
        self.rt.ledger.reset_counts(self.clock.step - 1)
        self.db.set_meta("status", RunStatus.RUNNING.value)
        self.db.commit()
        self._timed = self._timed_snapshots()

    def advance(self) -> StepReport:
        """One step, with any due timed snapshot before it and a periodic checkpoint after it."""

        due = [name for name, t in getattr(self, "_timed", []) if t <= self.clock.now and name not in self.snapshots()]
        if due:
            self._checkpoint(note="snapshot")
            for name in due:
                self.snapshot(name)
        rep = self.step()
        if self.clock.step % self.cfg.output.checkpoint_every_steps == 0:
            self._checkpoint()
        return rep

    def wind_down(self) -> RunStatus:
        """Checkpoint where the run stopped; take the final snapshot if the scenario is over."""

        status = RunStatus.COMPLETED if self.clock.now >= self.cfg.scenario.end else RunStatus.INTERRUPTED
        self._checkpoint(note="stopped")
        if status == RunStatus.COMPLETED and "final" in self.cfg.output.snapshots:
            self.snapshot("final")
        return status

    def finish(self, status: RunStatus) -> str:
        self.db.set_meta("status", status.value)
        self.db.commit()
        self.write_manifest()
        return status.value

    # ================================================================== snapshots
    def _timed_snapshots(self) -> list[tuple[str, datetime]]:
        out = []
        for item in self.cfg.output.snapshots:
            if item in ("initial", "final"):
                continue
            out.append((item.replace(":", "-"), datetime.fromisoformat(item)))
        return out

    def snapshots(self) -> dict[str, Any]:
        return dict(self.db.get_meta("snapshots", {}) or {})

    def snapshot(self, name: str) -> Path:
        """Copy the committed state to ``snapshots/<name>.sqlite`` (call right after a checkpoint)."""

        folder = self.run_dir / "snapshots"
        folder.mkdir(exist_ok=True)
        path = folder / f"{name}.sqlite"
        if path.exists():
            path.unlink()
        snaps = self.snapshots()
        snaps[name] = {"path": str(path.relative_to(self.run_dir)), "step": self.clock.step, "sim_time": iso(self.clock.now)}
        self.db.set_meta("snapshots", snaps)
        self.db.commit()
        copy = self.db.clone(path)
        copy.set_meta("snapshot", {"name": name, "run_id": self.run_id, **snaps[name]})
        copy.commit()
        copy.close()
        return path

    def check_scenario_unchanged(self) -> None:
        recorded = self.db.get_meta("scenario")
        if not recorded:
            return
        now = self.scenario.manifest()
        keys = ("sha256", "map_sha256", "events_sha256", "constraints_sha256", "agent_file_sha256", "agents", "candidacy_seed_policy")
        changed = [k for k in keys if recorded.get(k) != now.get(k)]
        if changed:
            raise RuntimeError(f"scenario files changed since this run started ({', '.join(changed)}); start a new run instead of resuming")

    def _abort(self, status: RunStatus, detail: str) -> None:
        self.db.rollback()
        self._invalidate()
        self.clock.step = int(self.db.get_meta("next_step", 0))
        self.db.set_meta("stop_detail", {"status": status.value, "detail": detail, "at_step": self.clock.step})
        totals = self.rt.ledger.totals()
        usage = self.rt.budget.snapshot()
        usage.update({"calls": int(totals["calls"] or 0), "input_tokens": int(totals["input_tokens"] or 0), "output_tokens": int(totals["output_tokens"] or 0)})
        self.db.set_meta("budget", usage)
        self.svc.events.log("run_stopped", self.clock.now, None, status=status.value, detail=detail)
        self.db.commit()

    def _invalidate(self) -> None:
        self.svc.states.invalidate()
        self.spatial.invalidate()
        self.world_state.invalidate()
        self.plans.invalidate()
        self.svc.store.reset_seq_cache()
        self.svc.traces.reset()
        self._last_frame = {}
        for hook in self.invalidate_hooks:
            hook()

    def _checkpoint(self, note: str = "") -> None:
        self.svc.states.flush()
        self.spatial.flush()
        self.world_state.flush()
        for hook in self.flush_hooks:
            hook()
        self._frame(self.clock.step - 1, keyframe=True)
        self.db.set_meta("next_step", self.clock.step)
        self.db.set_meta("sim_time", iso(self.clock.now))
        self.db.set_meta("budget", self.rt.budget.snapshot())
        self.db.execute(
            "INSERT INTO checkpoints(step, sim_time, json) VALUES(?,?,?) ON CONFLICT(step) DO UPDATE SET json=excluded.json",
            (self.clock.step, iso(self.clock.now), stable_json({"note": note, "budget": self.rt.budget.snapshot(), "wall": time.time()})),
        )
        self.db.commit()

    def step(self) -> StepReport:
        now = self.clock.now
        self._report = StepReport(self.clock.step, now)
        self._talk_requests = []
        self._busy = set()
        try:
            self._apply_interventions(now)
            for hook in self.before_step_hooks:
                hook(now)
            views = self.views()
            occupancy = self._occupancy(views)
            for aid in self.order:
                self._agent_step(aid, now, views, occupancy)
            self._resolve_talks(now, views)
            self._commit_moves(now)
            for hook in self.after_step_hooks:
                hook(now)
            self.svc.states.flush()
            self.spatial.flush()
            self.world_state.flush()
            for hook in self.flush_hooks:
                hook()
            self._frame(self.clock.step, keyframe=False)
        except BudgetExceeded as exc:
            raise RunStopped(RunStatus.BUDGET_EXHAUSTED, str(exc)) from exc
        except ReplayMiss as exc:
            raise RunStopped(RunStatus.FAILED, f"replay diverged: {exc}") from exc
        except ProviderError as exc:
            raise RunStopped(RunStatus.PROVIDER_FAILURE, str(exc)) from exc
        self.clock.advance()
        rep = self._report
        for cb in self.on_step:
            cb(rep)
        return rep

    # ================================================================== snapshot
    def view_of(self, aid: str) -> AgentView:
        st = self.svc.states.get(aid)
        ident = self.identities[aid]
        act = st.action
        partner = None
        if act.kind == "conversation" and act.conversation_id:
            conv = self.dialogue.get(act.conversation_id)
            if conv:
                pid = next((p for p in conv.participants if p != aid), None)
                partner = self.identities[pid].name if pid in self.identities else None
        activity = act.description if act.kind not in ("failed", "idle") else ""
        return AgentView(
            agent_id=aid,
            name=ident.name,
            tile=tuple(st.tile) if st.tile else (0, 0),
            activity=activity,
            predicate=act.predicate or "is",
            obj=act.object or activity,
            address=act.address,
            sleeping=is_sleep(act.description) and act.kind != "conversation",
            conversation_id=act.conversation_id if act.kind == "conversation" else None,
            conversation_partner=partner,
        )

    def views(self) -> dict[str, AgentView]:
        return {aid: self.view_of(aid) for aid in self.order}

    def _occupancy(self, views: dict[str, AgentView]) -> dict[str, set[str]]:
        occ: dict[str, set[str]] = {}
        for aid, v in views.items():
            here = self.world.arena_at(*v.tile)
            if here:
                occ.setdefault(here, set()).add(aid)
            st = self.svc.states.get(aid)
            if st.action.address and st.action.path:
                target = ":".join(st.action.address.split(":")[:3])
                occ.setdefault(target, set()).add(aid)
        return occ

    # ================================================================== interventions
    def _apply_interventions(self, now: datetime) -> None:
        applied = set(self.db.get_meta("interventions_applied", []))
        changed = False
        for it in self.interventions:
            if it["at"] > now or it["_index"] in applied:
                continue
            kind = it["kind"]
            if kind == "object_state":
                if not self.world.exists(it["address"]):
                    raise ValueError(f"intervention names an unknown object: {it['address']}")
                self.world_state.set_lasting(it["address"], it["state"], now, "intervention")
            elif kind == "ambient":
                tile = tuple(it["tile"])
                self.world_state.add_ambient(
                    AmbientEvent(
                        id=it.get("id", f"ambient{it['_index']}"),
                        tile=tile,
                        subject=it.get("subject", "fire"),
                        predicate=it.get("predicate", "is"),
                        object=it.get("object", "burning"),
                        description=it["description"],
                        started_at=now,
                        until=datetime.fromisoformat(str(it["until"])) if it.get("until") else None,
                        note=it.get("note"),
                    )
                )
            elif kind == "end_ambient":
                self.world_state.end_ambient(it["id"], now)
            elif kind == "inner_voice":
                ident = self.identities[it["agent"]]
                self.svc.remember(ident, it["text"], MemoryKind.OBSERVATION, MemoryOrigin.INNER_VOICE, now, metadata={"intervention": it["_index"]})
            else:
                raise ValueError(f"unknown intervention kind {kind!r}")
            applied.add(it["_index"])
            changed = True
            self.svc.events.log("intervention", now, it.get("agent"), **{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in it.items()})
        if changed:
            self.db.set_meta("interventions_applied", sorted(applied))

    # ================================================================== one agent
    def _agent_step(self, aid: str, now: datetime, views: dict[str, AgentView], occupancy: dict[str, set[str]]) -> None:
        ident = self.identities[aid]
        st = self.svc.states.get(aid)
        rep = self._report
        assert rep is not None
        if self.planner.enabled:
            self.planner.ensure_day(ident, now)

        # -------- perceive (snapshot) and remember what is new
        p = st.extra.get("perception") or {"vision_r": 8, "att_bandwidth": 8, "retention": 8}
        spatial = self.spatial.get(aid)
        moved = st.extra.get("last_perceived_tile") != list(views[aid].tile)
        res = self.perceiver.perceive(views[aid], p["vision_r"], p["att_bandwidth"], views, self.world_state, now, spatial, learn_space=moved)
        st.extra["last_perceived_tile"] = list(views[aid].tile)
        latest = self.svc.store.latest_observation_triples(aid, p["retention"])
        new: list[Percept] = []
        for pc in res.percepts:
            if pc.spo in latest:
                continue
            latest.add(pc.spo)
            origin = MemoryOrigin.EXECUTED_ACTION if pc.kind == "self" else MemoryOrigin.DIRECT_OBSERVATION
            self.svc.remember(
                ident,
                pc.description,
                MemoryKind.OBSERVATION,
                origin,
                now,
                subject=pc.subject,
                predicate=pc.predicate,
                object=pc.object,
                location=self.world.arena_at(*pc.tile) or self.world.sector_at(*pc.tile),
                source_event_id=pc.address or pc.agent_id,
                metadata={"percept": pc.kind, "distance": round(pc.distance, 2)},
            )
            rep.new_memories += 1
            new.append(pc)

        # -------- reflect
        if self.reflection.should_reflect(ident, now):
            out = self.reflection.run(ident, now)
            rep.reflections += 1 if out.get("stored") else 0

        # -------- follow the plan
        if aid not in self._busy:
            self._follow_plan(ident, now, occupancy, views)

        # -------- react to one focal percept
        if aid in self._busy or st.action.kind == "conversation":
            return
        considered: list[str] = st.extra.setdefault("considered", [])
        candidates = [pc for pc in new if pc.kind == "agent"]
        candidates += [
            pc for pc in res.percepts if pc.kind in ("ambient", "object") and (pc.kind == "ambient" or self._notable(pc)) and "|".join(pc.spo) not in considered
        ]
        asleep = is_sleep(st.action.description) and st.action.kind == "plan"  # own state after following the plan
        focal = focal_percept(candidates, sleeping=asleep)
        if focal is None:
            return
        key = "|".join(focal.spo)
        if key == st.last_reaction_key:
            return
        if focal.kind in ("ambient", "object"):
            considered.append(key)
            del considered[:-50]
        if focal.kind == "agent":
            other = views.get(focal.agent_id or "")
            if other is None or other.sleeping or other.conversation_id or st.action.kind == "wait":
                return  # released lets_react / lets_talk preconditions
        st.last_reaction_key = key
        can_talk = focal.kind == "agent" and self._can_talk(aid, focal.agent_id or "", now, views)
        dec = self.reaction.decide(
            ident,
            focal,
            now,
            status=self._status(ident, st.action),
            can_talk=can_talk,
            observed_name=self.identities[focal.agent_id].name if focal.agent_id in self.identities else None,
        )
        self.svc.events.log(
            "reaction",
            now,
            aid,
            observation=focal.description,
            decision=dec.decision,
            reason=dec.reason,
            new_activity=dec.new_activity,
            minutes=dec.minutes,
            context=dec.context,
            trace_ids=dec.trace_ids,
            call_ids=dec.call_ids,
        )
        if dec.decision == "talk" and dec.partner_id:
            self._talk_requests.append(TalkRequest(aid, dec.partner_id, focal, dec.reason))
        elif dec.decision == "react" and dec.new_activity:
            item = self.planner.insert(
                ident, now, dec.new_activity, dec.minutes or 10, source="reaction", metadata={"observation": focal.description, "reason": dec.reason}
            )
            self._start_action(ident, item, now, occupancy, views)
        elif dec.decision == "wait":
            item = self.planner.insert(
                ident,
                now,
                f"waiting ({dec.reason.rstrip('.')})" if dec.reason else "waiting",
                dec.minutes or 5,
                source="wait",
                metadata={"observation": focal.description},
                displace=False,
            )
            self._start_action(ident, item, now, occupancy, views)

    def _notable(self, pc: Percept) -> bool:
        st = self.world_state.get(pc.address or "")
        return st.lasting != IDLE and (st.in_use is None or st.in_use == IDLE)

    def _status(self, ident: AgentIdentity, act: ActionState) -> str:
        if act.kind in ("failed", "idle") or not act.description:
            return f"{ident.name} is idle"
        where = f" at {act.address.split(':', 1)[-1]}" if act.address else ""
        return f"{ident.name} is {act.description}{where}"

    def _can_talk(self, aid: str, pid: str, now: datetime, views: dict[str, AgentView]) -> bool:
        if pid not in views or now.hour >= self.cfg.dialogue.no_chat_after_hour:
            return False
        me, other = views[aid], views[pid]
        if me.sleeping or other.sleeping or me.conversation_id or other.conversation_id:
            return False
        if pid in self._busy or aid in self._busy:
            return False
        if self.svc.states.get(pid).action.kind == "wait":
            return False
        until = self.svc.states.get(aid).cooldown_until.get(pid)
        return not (until and now < until)

    # ================================================================== actions
    def _follow_plan(self, ident: AgentIdentity, now: datetime, occupancy: dict[str, set[str]], views: dict[str, AgentView]) -> None:
        st = self.svc.states.get(ident.id)
        act = st.action
        if act.plan_item_id and not act.finished(now) and act.kind != "idle":
            return
        if act.plan_item_id:
            self.planner.mark_done(act.plan_item_id, now)
        task = self.planner.current_task(ident, now) if self.planner.enabled else None
        if task is None:
            if act.kind != "idle":
                self.world_state.release(ident.id)
                st.action = ActionState(kind="idle", start=now, description="")
            return
        if task.id == act.plan_item_id and not act.finished(now):
            return
        self._start_action(ident, task, now, occupancy, views)

    def _start_action(self, ident: AgentIdentity, task: PlanItem, now: datetime, occupancy: dict[str, set[str]], views: dict[str, AgentView]) -> None:
        st = self.svc.states.get(ident.id)
        here: Tile = tuple(st.tile) if st.tile else (0, 0)
        s, a, _ = self.world.names_at(*here)
        act = ActionState(plan_item_id=task.id, description=task.description, start=task.start, duration_min=task.duration_min, kind="plan")
        self.world_state.release(ident.id)
        rep = self._report
        if rep is not None:
            rep.actions_started += 1
        if task.source == "conversation":
            act.kind = "conversation"
            act.conversation_id = task.metadata.get("conversation_id")
            meet = task.metadata.get("meeting_tile")
            act.target_tile = tuple(meet) if meet else here
            act.address = self.world.address_at(*act.target_tile, level="arena") or self.world.address_at(*act.target_tile, level="sector")
            act.path = self.nav.path(here, act.target_tile) or []
            act.predicate, act.object = "chat with", task.metadata.get("partner_name", "")
        elif task.source == "wait":
            act.kind = "wait"
            act.address = self.world.address_at(*here, level="arena") or self.world.address_at(*here, level="sector")
            act.target_tile = here
            act.predicate, act.object = "is", "waiting"
        else:

            def check(address: str) -> Verdict:
                return self.constraints.check(ident, address, now, occupancy, current_arena=self.world.arena_at(*here)) if self.constraints.active else ALLOW

            reuse = st.extra.get("last_location") if self.cfg.location.reuse_within_block else None
            if (
                reuse
                and reuse.get("block") == task.parent_id
                and reuse.get("address")
                and self.world.exists(reuse["address"])
                and check(":".join(reuse["address"].split(":")[:3])).allowed
            ):
                loc = LocationResult(reuse["address"], choices=[{"level": "reused", "choice": reuse["address"], "asked": False}])
            else:
                loc = self.locations.choose(ident, task.description, now, (s, a), self.spatial.get(ident.id), check=check)
            if loc.address and not loc.failure and loc.verdict.allowed:
                st.extra["last_location"] = {"block": task.parent_id, "address": loc.address}
            if loc.verdict.rule == "occupied":
                wait = self.planner.insert(
                    ident,
                    now,
                    f"waiting for the {loc.address.split(':')[-1] if loc.address else 'room'} to be free",
                    self.constraints.wait_minutes,
                    source="wait",
                    displace=False,
                )
                self._start_action(ident, wait, now, occupancy, views)
                return
            if loc.failure or not loc.address:
                act.kind = "failed"
                act.address = None
                st.failures += 1
                self.svc.events.log("action_failure", now, ident.id, task=task.id, activity=task.description, reason=loc.failure, choices=loc.choices)
                st.action = act
                return
            act.address = loc.address
            others = {tuple(v.tile) for k, v in views.items() if k != ident.id}
            pick = self.nav.nearest(here, self.world.walkable_tiles_for(loc.address), avoid=others)
            if pick is None:
                act.kind = "failed"
                st.failures += 1
                self.svc.events.log("action_failure", now, ident.id, task=task.id, activity=task.description, reason=f"no reachable tile for {loc.address}")
                st.action = act
                return
            act.target_tile = pick[0]
            act.path = self.nav.path(here, pick[0]) or []
            self._ground(ident, act, now)
            arena = ":".join(loc.address.split(":")[:3])
            occupancy.setdefault(arena, set()).add(ident.id)
            self.svc.events.log(
                "action",
                now,
                ident.id,
                task=task.id,
                activity=task.description,
                address=loc.address,
                choices=loc.choices,
                rejections=loc.rejections,
                path_len=len(act.path),
                triple=[act.subject, act.predicate, act.object],
                object_state=act.object_state,
                believed_state=self.spatial.get(ident.id).believed_state(loc.address) if loc.address.count(":") == 3 else None,
                seen_lasting=self.spatial.get(ident.id).seen_lasting(loc.address) if loc.address.count(":") == 3 else None,
                actual_lasting=self.world_state.get(loc.address).lasting if loc.address.count(":") == 3 else None,
                lasting_state=act.lasting_state,
            )
        st.action = act
        self.planner.mark_active(task)

    def _ground(self, ident: AgentIdentity, act: ActionState, now: datetime) -> None:
        parts = (act.address or "").split(":")
        has_object = len(parts) == 4
        obj_name = parts[-1] if has_object else (parts[-1] if parts else "area")
        place = ": ".join(parts[1:3]) if len(parts) >= 3 else (parts[1] if len(parts) > 1 else "outside")
        believed = self.spatial.get(ident.id).believed_state(act.address or "") if has_object else None
        try:
            out = self.svc.gateway.run(
                "action_grounding",
                {
                    "agent_name": ident.name,
                    "activity": act.description,
                    "place": place,
                    "object_name": obj_name,
                    "object_condition": believed or IDLE,
                    "_name": ident.name,
                    "_activity": act.description,
                    "_object": obj_name if has_object else "",
                    "_condition": believed or IDLE,
                },
                agent_id=ident.id,
                sim_time=now,
                purpose="action:grounding",
            )
        except TaskFailed:
            act.subject, act.predicate, act.object = ident.name, "is", act.description
            return
        o = out.output
        act.subject, act.predicate, act.object = ident.name, o.predicate.strip() or "is", o.object.strip() or act.description
        if has_object:
            act.object_state = (o.object_state or IDLE).strip()
            lasting = (o.lasting_state or "").strip()
            if lasting and lasting.lower() not in ("null", "none", IDLE):
                act.lasting_state = lasting

    # ================================================================== conversations
    def _resolve_talks(self, now: datetime, views: dict[str, AgentView]) -> None:
        for req in self._talk_requests:
            a, b = req.initiator, req.partner
            if a in self._busy or b in self._busy:
                self.svc.events.log("talk_skipped", now, a, partner=b, reason="a participant is already in a conversation this step")
                continue
            ia, ib = self.identities[a], self.identities[b]
            sa, sb = self.svc.states.get(a), self.svc.states.get(b)
            loc = self.world.arena_at(*views[a].tile) or self.world.sector_at(*views[a].tile)
            conv = self.dialogue.run(
                Side(ia, self._status(ia, sa.action), views[b].description),
                Side(ib, self._status(ib, sb.action), views[a].description),
                now,
                loc,
                trigger=req.percept.description,
            )
            self._busy |= {a, b}
            if self._report is not None:
                self._report.conversations.append(conv.id)
            cooldown = timedelta(minutes=self.cfg.dialogue.cooldown_minutes)
            end = conv.ended_at or now
            sa.cooldown_until[b] = end + cooldown
            sb.cooldown_until[a] = end + cooldown
            if not conv.utterances:
                continue
            meet = self.nav.meeting_tile(views[a].tile, views[b].tile) or views[a].tile
            minutes = int(conv.metadata.get("minutes", 1))
            for me, other in ((ia, ib), (ib, ia)):
                item = self.planner.insert(
                    me,
                    now,
                    f"chatting with {other.name}",
                    minutes,
                    source="conversation",
                    metadata={"conversation_id": conv.id, "meeting_tile": list(meet), "partner_name": other.name},
                )
                self._start_action(me, item, now, {}, views)

    # ================================================================== commit
    def _commit_moves(self, now: datetime) -> None:
        for aid in self.order:
            st = self.svc.states.get(aid)
            act = st.action
            if act.path:
                nxt = act.path.pop(0)
                st.tile = (int(nxt[0]), int(nxt[1]))
            if (
                not act.path
                and act.address
                and act.kind == "plan"
                and act.address.count(":") == 3
                and act.target_tile
                and tuple(st.tile) == tuple(act.target_tile)
            ):
                if self.world_state.user_of(act.address) != aid:
                    self.world_state.use(act.address, aid, act.object_state, now)
                if act.lasting_state:
                    self.world_state.set_lasting(act.address, act.lasting_state, now, "agent")
                    self.svc.events.log("object_state", now, aid, address=act.address, lasting=act.lasting_state)
                    act.lasting_state = None

    def _frame(self, step: int, keyframe: bool) -> None:
        """Agent positions/actions after ``step`` (deltas; full keyframes at checkpoints)."""

        if not self.cfg.output.record_frames:
            return
        cur: dict[str, list[Any]] = {}
        for aid in self.order:
            st = self.svc.states.get(aid)
            a = st.action
            cur[aid] = [
                int(st.tile[0]) if st.tile else None,
                int(st.tile[1]) if st.tile else None,
                a.description if a.kind not in ("failed", "idle") else "",
                a.kind,
                a.address,
                a.conversation_id if a.kind == "conversation" else None,
            ]
        delta = cur if keyframe else {k: v for k, v in cur.items() if self._last_frame.get(k) != v}
        self._last_frame = cur
        if not delta and not keyframe:
            return
        self.db.execute(
            "INSERT INTO frames(step, sim_time, json) VALUES(?,?,?) ON CONFLICT(step) DO UPDATE SET json=excluded.json",
            (
                step,
                iso(self.clock.now),
                json.dumps({"key": keyframe, "agents": delta, "objects": self.world_state.to_json()["objects"] if keyframe else None}, separators=(",", ":")),
            ),
        )

    # ================================================================== manifest
    def write_manifest(self) -> dict[str, Any]:
        cfg = self.cfg
        totals = self.rt.ledger.totals()
        manifest = {
            "run_id": self.run_id,
            "mode": cfg.run_mode,
            "label": cfg.run.label,
            "mock_llm": cfg.providers.llm.kind == "mock",
            "mock_embeddings": cfg.providers.embeddings.kind == "mock-hash",
            "research_grade": cfg.providers.llm.kind not in ("mock",) and cfg.providers.embeddings.kind != "mock-hash",
            "status": self.status,
            "stop_detail": self.db.get_meta("stop_detail"),
            "next_step": self.clock.step,
            "sim_time": iso(self.clock.now),
            "scenario": self.db.get_meta("scenario") or self.scenario.manifest(),
            "config_sha256": __import__("hashlib").sha256(cfg.model_dump_json().encode()).hexdigest(),
            "fidelity": cfg.fidelity_table(),
            "prompts": self.rt.registry.manifest(),
            "llm": self.rt.provider.describe() if hasattr(self.rt.provider, "describe") else {"provider": self.rt.provider_name},
            "embeddings": self.rt.embeddings.describe(),
            "ledger": {k: v for k, v in totals.items() if k != "by_task"},
            "calls_by_task": totals.get("by_task"),
            "budget": {"limits": self.rt.budget.limits(), "usage": self.rt.budget.snapshot()},
            "code": {"package_version": __version__, "git_commit": git_commit(), "python": platform.python_version()},
            "replay_of": {"run_id": self.replay_scope, "dir": str(self.replay_from)} if self.replay_from else None,
            "game": self.game.manifest() if self.game is not None else None,
        }
        (self.run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
        return manifest

    def close(self) -> None:
        self.db.close()
        self.rt.ledger.close()


# ====================================================================== helpers
def new_run_dir(cfg: GAConfig, run_id: str | None = None) -> Path:
    root = repo_path(cfg.run.output_dir)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rid = run_id or f"{stamp}-{cfg.run.name}-{cfg.run_mode}"
    d = root / rid
    if d.exists() and any(d.iterdir()):
        raise FileExistsError(f"run directory {d} already exists")
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_config(cfg: GAConfig, run_dir: Path) -> None:
    (run_dir / "config.yaml").write_text(yaml.safe_dump(json.loads(cfg.model_dump_json()), sort_keys=False, allow_unicode=True))


def load_run_config(run_dir: Path, overrides: list[str] | None = None) -> GAConfig:
    from ..config import apply_overrides

    raw = yaml.safe_load((run_dir / "config.yaml").read_text())
    if overrides:
        raw = apply_overrides(raw, overrides)
    return GAConfig.model_validate(raw)


def describe_time(t: datetime) -> str:
    return long_time(t)


__all__ = ["Simulation", "RunStopped", "new_run_dir", "save_config", "load_run_config", "parse_iso"]
