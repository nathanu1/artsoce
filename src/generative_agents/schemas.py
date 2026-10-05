"""Typed, validated data models shared by every module.

Simulation time is always a naive ``datetime`` in the scenario's own calendar; wall-clock
time never enters agent state. See docs/reproduction_spec.md (B-1, B-2, B-4) for the memory
fields and provenance categories.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoryKind(StrEnum):
    """Semantic memory type (paper §4: observation, reflection, plan)."""

    OBSERVATION = "observation"
    REFLECTION = "reflection"
    PLAN = "plan"


class MemoryOrigin(StrEnum):
    """Where a memory came from. Keeps statements, intentions and facts apart (spec B-4)."""

    SEED = "seed"  # authored initial memory (paper p. 5)
    DIRECT_OBSERVATION = "direct_observation"  # perceived event in the world
    STATEMENT = "statement"  # what another agent said; not world truth
    OWN_STATEMENT = "own_statement"  # what this agent said
    CONVERSATION = "conversation"  # observational transcript summary
    EXECUTED_ACTION = "executed_action"  # an action this agent actually performed
    INFERENCE = "inference"  # reflection insight (or compat post-conversation thought)
    INTENTION = "intention"  # plan entry; not proof of action
    INNER_VOICE = "inner_voice"  # logged user directive (paper p. 6)
    SYSTEM_FEEDBACK = "system_feedback"  # engine rejection the agent perceived


class Memory(BaseModel):
    """One record in an agent's private memory stream."""

    model_config = ConfigDict(frozen=False)

    id: str
    owner_id: str
    kind: MemoryKind
    origin: MemoryOrigin
    description: str
    created_at: datetime
    last_accessed_at: datetime
    importance: int = Field(ge=1, le=10)
    embedding_model: str = ""
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    location: str | None = None
    source_event_id: str | None = None
    conversation_id: str | None = None
    speaker_id: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    depth: int = 0
    plan_id: str | None = None
    seed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def spo(self) -> tuple[str | None, str | None, str | None]:
        return (self.subject, self.predicate, self.object)

    @property
    def is_idle(self) -> bool:
        return self.description.rstrip(". ").endswith("is idle")


class AgentIdentity(BaseModel):
    """Authored identity (paper §3.1; released scratch.json fields)."""

    id: str
    name: str
    first_name: str
    last_name: str
    age: int
    innate: str
    learned: str
    currently: str
    lifestyle: str
    living_area: str
    daily_plan_req: str = ""

    @property
    def traits(self) -> str:
        return self.innate


class PlanLevel(StrEnum):
    DAY = "day"
    HOUR = "hour"
    TASK = "task"


class PlanStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    DONE = "done"
    SUPERSEDED = "superseded"  # replaced by a replan; kept for history
    FAILED = "failed"


class PlanItem(BaseModel):
    """A plan entry: location, start, duration, description (paper §4.3, p. 11)."""

    id: str
    agent_id: str
    level: PlanLevel
    parent_id: str | None = None
    day: str  # ISO date of the plan day
    start: datetime
    duration_min: int = Field(gt=0)
    description: str
    location: str | None = None
    status: PlanStatus = PlanStatus.PLANNED
    created_at: datetime
    source: str = "generated"  # generated | replan | reaction | conversation | repair
    memory_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def end(self) -> datetime:
        from datetime import timedelta

        return self.start + timedelta(minutes=self.duration_min)


class ActionState(BaseModel):
    """The action an agent is currently executing."""

    plan_item_id: str | None = None
    description: str = ""
    address: str | None = None  # world:sector:arena[:object]
    start: datetime | None = None
    duration_min: int = 0
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    object_state: str | None = None  # state of the target object while in use
    lasting_state: str | None = None  # lasting condition left behind (applied once on arrival)
    path: list[tuple[int, int]] = Field(default_factory=list)
    target_tile: tuple[int, int] | None = None
    conversation_id: str | None = None
    kind: str = "plan"  # plan | conversation | wait | reaction | idle | failed

    @field_validator("path", mode="before")
    @classmethod
    def _tuples(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [tuple(p) for p in v]
        return v

    def end(self) -> datetime | None:
        from datetime import timedelta

        if self.start is None:
            return None
        return self.start + timedelta(minutes=self.duration_min)

    def finished(self, now: datetime) -> bool:
        end = self.end()
        return end is None or now >= end


class Utterance(BaseModel):
    speaker_id: str
    text: str
    sim_time: datetime
    end_conversation: bool = False


class Conversation(BaseModel):
    id: str
    participants: list[str]
    initiator_id: str
    started_at: datetime
    ended_at: datetime | None = None
    location: str | None = None
    utterances: list[Utterance] = Field(default_factory=list)
    summary: str | None = None
    status: str = "active"  # active | completed | failed
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorldEvent(BaseModel):
    """Something visible in the world at a tile (agent action or object state)."""

    subject: str  # agent name, or object address
    predicate: str
    object: str
    description: str
    tile: tuple[int, int]
    is_agent: bool = False
    arena: str | None = None

    @property
    def spo(self) -> tuple[str, str, str]:
        return (self.subject, self.predicate, self.object)


class RunMode(StrEnum):
    MOCK = "mock"
    LIVE = "live"
    REPLAY = "replay"


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    PROVIDER_FAILURE = "provider_failure"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
