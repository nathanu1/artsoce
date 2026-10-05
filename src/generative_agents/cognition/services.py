"""The bundle of services every cognitive module uses, plus the one door into memory.

``Services.remember`` is the only way memories are created during a run: it scores
importance (or takes a caller-provided score), embeds the text and appends the record.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..config import GAConfig
from ..db import Database
from ..memory.retrieval import Retriever
from ..memory.store import MemoryStore
from ..memory.trace import TraceStore
from ..providers.embeddings import EmbeddingService
from ..providers.gateway import LLMGateway
from ..schemas import AgentIdentity, Memory, MemoryKind, MemoryOrigin
from ..simulation.state import EventLog, StateStore
from .importance import ImportanceScorer

# Which origins count as newly *perceived* for the reflection trigger (spec D-5, E-1).
PERCEIVED_ORIGINS = {
    MemoryOrigin.DIRECT_OBSERVATION,
    MemoryOrigin.STATEMENT,
    MemoryOrigin.OWN_STATEMENT,
    MemoryOrigin.CONVERSATION,
    MemoryOrigin.EXECUTED_ACTION,
    MemoryOrigin.SYSTEM_FEEDBACK,
    MemoryOrigin.INNER_VOICE,
}

IMPORTANCE_KIND = {
    MemoryKind.OBSERVATION: "observation",
    MemoryKind.REFLECTION: "thought",
    MemoryKind.PLAN: "thought",
}


@dataclass
class Services:
    cfg: GAConfig
    db: Database
    store: MemoryStore
    gateway: LLMGateway
    embeddings: EmbeddingService
    retriever: Retriever
    importance: ImportanceScorer
    traces: TraceStore
    states: StateStore
    events: EventLog
    identities: dict[str, AgentIdentity]

    def remember(
        self,
        identity: AgentIdentity,
        text: str,
        kind: MemoryKind,
        origin: MemoryOrigin,
        now: datetime,
        *,
        importance: int | None = None,
        importance_kind: str | None = None,
        **fields: Any,
    ) -> Memory:
        if importance is None:
            ik = importance_kind or ("conversation" if origin in (MemoryOrigin.CONVERSATION,) else IMPORTANCE_KIND[kind])
            importance = self.importance.score(identity, text, ik, now)
        vec = self.embeddings.embed_one(text)
        mem = self.store.add(
            owner_id=identity.id,
            kind=kind,
            origin=origin,
            description=text,
            created_at=now,
            importance=importance,
            embedding_model=self.embeddings.model_key,
            vector=vec,
            **fields,
        )
        if origin in PERCEIVED_ORIGINS:
            state = self.states.get(identity.id)
            state.reflection_accumulator += importance
            state.reflection_ele_n += 1
            if state.reflection_countdown is not None:
                state.reflection_countdown -= importance
        return mem
