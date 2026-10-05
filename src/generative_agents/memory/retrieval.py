"""Three-factor memory retrieval (paper §4.1 p. 9) and a released-code compatibility mode.

Paper mode (spec C-1 … C-8):

    hours = max(0, (now - last_accessed) / 1 h)
    recency    = decay ** hours                       (decay = 0.995)
    importance = stored integer
    relevance  = cosine(embedding(memory), embedding(query))
    each component min-max normalized over the eligible candidates (constant → 0.5)
    score = a_r * recency + a_i * importance + a_v * relevance      (all a = 1)

Selection is the longest prefix of the ranking that fits the token budget and item cap. All
scores are computed before any access time changes, and only delivered memories are touched.

Compat mode (spec C-9) reproduces ``new_retrieve`` in the released ``retrieve.py``:
candidates exclude memories whose text contains "idle"; recency is ``decay ** i`` for
positions i = 1..n of the candidates sorted by last access ascending (so the oldest access
gets the largest raw value); global weights 0.5 (recency), 3 (relevance), 2 (importance)
multiply the per-agent weights.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np

from ..schemas import Memory, MemoryKind
from .store import MemoryStore

COMPAT_GLOBAL_WEIGHTS = {"recency": 0.5, "relevance": 3.0, "importance": 2.0}  # retrieve.py:244


@dataclass(frozen=True)
class Weights:
    recency: float = 1.0
    importance: float = 1.0
    relevance: float = 1.0


@dataclass
class RetrievalSettings:
    mode: str = "paper"  # paper | released_code
    weights: Weights = field(default_factory=Weights)
    decay_per_hour: float = 0.995
    compat_decay: float = 0.995
    equal_component_value: float = 0.5
    budget_tokens: int | None = 1200
    max_items: int | None = 30
    tokens_per_char: float = 0.25

    @classmethod
    def from_config(cls, cfg: Any) -> RetrievalSettings:
        return cls(
            mode=cfg.mode,
            weights=Weights(cfg.weights.recency, cfg.weights.importance, cfg.weights.relevance),
            decay_per_hour=cfg.decay_per_hour,
            compat_decay=cfg.compat_decay,
            equal_component_value=cfg.equal_component_value,
            budget_tokens=cfg.budget_tokens,
            max_items=cfg.max_items,
            tokens_per_char=cfg.tokens_per_char,
        )


@dataclass
class Candidate:
    memory: Memory
    raw_recency: float
    raw_importance: float
    raw_relevance: float
    norm_recency: float = 0.0
    norm_importance: float = 0.0
    norm_relevance: float = 0.0
    score: float = 0.0
    tokens: int = 0
    zero_norm: bool = False
    access_position: int | None = None  # compat mode only
    rank: int = 0
    delivered: bool = False

    def components(self, w: Weights, mode: str) -> dict[str, float]:
        g = COMPAT_GLOBAL_WEIGHTS if mode == "released_code" else {"recency": 1.0, "relevance": 1.0, "importance": 1.0}
        return {
            "recency": g["recency"] * w.recency * self.norm_recency,
            "importance": g["importance"] * w.importance * self.norm_importance,
            "relevance": g["relevance"] * w.relevance * self.norm_relevance,
        }


@dataclass
class RetrievalResult:
    query: str
    agent_id: str
    now: datetime
    mode: str
    weights: Weights
    candidates: list[Candidate]  # ranked, all eligible
    excluded: list[dict[str, Any]]
    budget_tokens: int | None
    max_items: int | None
    used_tokens: int = 0
    trace_id: str | None = None

    @property
    def delivered(self) -> list[Memory]:
        return [c.memory for c in self.candidates if c.delivered]

    def explain(self, a_id: str, b_id: str) -> dict[str, Any]:
        """Why memory ``a_id`` ranked above or below ``b_id`` (spec C-11)."""

        by_id = {c.memory.id: c for c in self.candidates}
        if a_id not in by_id or b_id not in by_id:
            raise KeyError("both memories must be eligible candidates of this retrieval")
        a, b = by_id[a_id], by_id[b_id]
        ca, cb = a.components(self.weights, self.mode), b.components(self.weights, self.mode)
        diffs = {k: ca[k] - cb[k] for k in ca}
        total = a.score - b.score
        lead = max(diffs, key=lambda k: diffs[k])
        drag = min(diffs, key=lambda k: diffs[k])
        if math.isclose(total, 0.0, abs_tol=1e-12):
            verdict = "Tied on score; the deterministic tie-break decided the order."
        else:
            first, second = (a, b) if total > 0 else (b, a)
            verdict = (
                f"{first.memory.id} outranks {second.memory.id} by {abs(total):.3f}. "
                f"Largest push from {lead if total > 0 else drag} ({diffs[lead if total > 0 else drag]:+.3f})."
            )
        return {
            "a": {"id": a.memory.id, "rank": a.rank, "score": a.score, "components": ca},
            "b": {"id": b.memory.id, "rank": b.rank, "score": b.score, "components": cb},
            "difference": diffs,
            "score_difference": total,
            "verdict": verdict,
        }

    def to_trace(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "agent_id": self.agent_id,
            "sim_time": self.now.isoformat(),
            "mode": self.mode,
            "weights": self.weights.__dict__,
            "budget_tokens": self.budget_tokens,
            "max_items": self.max_items,
            "used_tokens": self.used_tokens,
            "excluded": self.excluded,
            "candidates": [
                {
                    "id": c.memory.id,
                    "rank": c.rank,
                    "kind": c.memory.kind.value,
                    "origin": c.memory.origin.value,
                    "description": c.memory.description,
                    "raw": {"recency": c.raw_recency, "importance": c.raw_importance, "relevance": c.raw_relevance},
                    "normalized": {"recency": c.norm_recency, "importance": c.norm_importance, "relevance": c.norm_relevance},
                    "score": c.score,
                    "tokens": c.tokens,
                    "zero_norm": c.zero_norm,
                    "access_position": c.access_position,
                    "delivered": c.delivered,
                }
                for c in self.candidates
            ],
            "delivered": [c.memory.id for c in self.candidates if c.delivered],
        }


def normalize_minmax(values: np.ndarray, equal_value: float = 0.5) -> np.ndarray:
    """Min-max scale to [0, 1]; a constant vector maps to ``equal_value`` (retrieve.py:96-99)."""

    if values.size == 0:
        return values.astype(np.float64)
    lo, hi = float(np.min(values)), float(np.max(values))
    if not math.isfinite(lo) or not math.isfinite(hi):
        raise ValueError("non-finite retrieval component")
    if hi - lo <= 1e-12:
        return np.full(values.shape, equal_value, dtype=np.float64)
    return (values.astype(np.float64) - lo) / (hi - lo)


def cosine_to(matrix: np.ndarray, query: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cosine of each row with ``query``; zero-norm rows (or a zero query) give 0 and are flagged."""

    if matrix.size == 0:
        return np.zeros(0), np.zeros(0, dtype=bool)
    m = matrix.astype(np.float64)
    q = query.astype(np.float64)
    row_norms = np.linalg.norm(m, axis=1)
    q_norm = float(np.linalg.norm(q))
    zero = (row_norms <= 1e-12) | (q_norm <= 1e-12)
    denom = np.where(zero, 1.0, row_norms * (q_norm if q_norm > 1e-12 else 1.0))
    sims = np.where(zero, 0.0, (m @ q) / denom)
    return np.clip(sims, -1.0, 1.0), zero


def estimate_tokens(text: str, tokens_per_char: float) -> int:
    return max(1, math.ceil(len(text) * tokens_per_char))


def rank_key(c: Candidate) -> tuple:
    """score ↓, last access ↓, creation ↓, id ↑ (spec C-8)."""

    return (-c.score, -c.memory.last_accessed_at.timestamp(), -c.memory.created_at.timestamp(), c.memory.id)


class Retriever:
    def __init__(
        self,
        store: MemoryStore,
        embedder: Any,
        settings: RetrievalSettings,
        *,
        trace_sink: Callable[[RetrievalResult, str | None], str | None] | None = None,
    ):
        self.store = store
        self.embedder = embedder
        self.settings = settings
        self.trace_sink = trace_sink

    def candidates_for(
        self,
        agent_id: str,
        now: datetime,
        *,
        kinds: Iterable[MemoryKind] | None = None,
        extra_filter: Callable[[Memory], bool] | None = None,
    ) -> tuple[list[Memory], list[dict[str, Any]]]:
        mems = self.store.for_agent(agent_id, kinds=kinds)
        eligible: list[Memory] = []
        excluded: list[dict[str, Any]] = []
        for m in mems:
            if m.created_at > now:
                excluded.append({"id": m.id, "reason": "created after query time"})
            elif self.settings.mode == "released_code" and "idle" in m.description:
                excluded.append({"id": m.id, "reason": "released code drops 'idle' memories (retrieve.py:226)"})
            elif extra_filter is not None and not extra_filter(m):
                excluded.append({"id": m.id, "reason": "filtered by caller"})
            else:
                eligible.append(m)
        return eligible, excluded

    def score(self, memories: list[Memory], query: str, now: datetime) -> list[Candidate]:
        if not memories:
            return []
        s = self.settings
        vectors = self.store.vectors_for(memories)
        qvec = self.embedder.embed_one(query)
        relevance, zero = cosine_to(vectors, qvec)
        importance = np.array([m.importance for m in memories], dtype=np.float64)
        positions: list[int | None] = [None] * len(memories)
        if s.mode == "released_code":
            order = sorted(range(len(memories)), key=lambda i: (memories[i].last_accessed_at, memories[i].id))
            recency = np.zeros(len(memories))
            for pos, idx in enumerate(order, start=1):
                recency[idx] = s.compat_decay**pos
                positions[idx] = pos
        else:
            hours = np.array([max(0.0, (now - m.last_accessed_at).total_seconds() / 3600.0) for m in memories])
            recency = np.power(s.decay_per_hour, hours)
        nr = normalize_minmax(recency, s.equal_component_value)
        ni = normalize_minmax(importance, s.equal_component_value)
        nv = normalize_minmax(relevance, s.equal_component_value)
        out: list[Candidate] = []
        for i, m in enumerate(memories):
            c = Candidate(
                memory=m,
                raw_recency=float(recency[i]),
                raw_importance=float(importance[i]),
                raw_relevance=float(relevance[i]),
                norm_recency=float(nr[i]),
                norm_importance=float(ni[i]),
                norm_relevance=float(nv[i]),
                tokens=estimate_tokens(m.description, s.tokens_per_char),
                zero_norm=bool(zero[i]),
                access_position=positions[i],
            )
            c.score = float(sum(c.components(s.weights, s.mode).values()))
            if not math.isfinite(c.score):
                raise ValueError(f"non-finite score for {m.id}")
            out.append(c)
        out.sort(key=rank_key)
        for rank, c in enumerate(out, start=1):
            c.rank = rank
        return out

    def retrieve(
        self,
        agent_id: str,
        query: str,
        now: datetime,
        *,
        kinds: Iterable[MemoryKind] | None = None,
        extra_filter: Callable[[Memory], bool] | None = None,
        budget_tokens: int | None = -1,
        max_items: int | None = -1,
        commit_access: bool = True,
        purpose: str | None = None,
    ) -> RetrievalResult:
        s = self.settings
        budget = s.budget_tokens if budget_tokens == -1 else budget_tokens
        cap = s.max_items if max_items == -1 else max_items
        eligible, excluded = self.candidates_for(agent_id, now, kinds=kinds, extra_filter=extra_filter)
        ranked = self.score(eligible, query, now)
        used = 0
        delivered = 0
        for c in ranked:
            if cap is not None and delivered >= cap:
                break
            if budget is not None and used + c.tokens > budget:
                break  # prefix policy: stop at the first memory that does not fit
            c.delivered = True
            used += c.tokens
            delivered += 1
        result = RetrievalResult(
            query=query,
            agent_id=agent_id,
            now=now,
            mode=s.mode,
            weights=s.weights,
            candidates=ranked,
            excluded=excluded,
            budget_tokens=budget,
            max_items=cap,
            used_tokens=used,
        )
        if commit_access:
            self.store.touch([c.memory.id for c in ranked if c.delivered], now)
            for c in ranked:
                if c.delivered:
                    c.memory.last_accessed_at = now
        if self.trace_sink is not None:
            result.trace_id = self.trace_sink(result, purpose)
        return result

    def retrieve_many(self, agent_id: str, queries: list[str], now: datetime, **kwargs: Any) -> list[Memory]:
        """Union of several queries' delivered memories, in first-seen order (no duplicates)."""

        seen: dict[str, Memory] = {}
        for q in queries:
            for m in self.retrieve(agent_id, q, now, **kwargs).delivered:
                seen.setdefault(m.id, m)
        return list(seen.values())


def keyword_lookup(store: MemoryStore, agent_id: str, keywords: Iterable[str]) -> list[Memory]:
    """Released-code reaction context (retrieve.py:16-45): memories whose subject or object
    matches the perceived event's subject, predicate or object. Unscored; no access update."""

    keys = {k.lower() for k in keywords if k}
    out = []
    for m in store.for_agent(agent_id):
        terms = {t.lower() for t in (m.subject, m.object) if t}
        terms |= {t.split(":")[-1].lower() for t in terms}
        if keys & terms:
            out.append(m)
    return out
