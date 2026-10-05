"""Cached dynamic summary (paper Appendix A p. 21; spec F-1 … F-3).

The summary combines name, age and traits with three LLM summaries of memories retrieved for
"[name]'s core characteristics", "[name]'s current daily occupation" and "[name]'s feeling
about their recent progress in life". It is cached per memory mask and refreshed every
``refresh_every_minutes`` of simulated time or on a new day. Ablated interview conditions
build their own summary from their permitted memories only.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..memory.masks import FULL, MemoryMask
from ..providers.base import TaskFailed
from ..schemas import AgentIdentity
from ..simulation.state import SummaryCache
from .context import bullet, identity_block, short_identity
from .services import Services

ASPECTS = (
    ("core", "{name}'s core characteristics"),
    ("occupation", "{name}'s current daily occupation"),
    ("feeling", "{name}'s feeling about their recent progress in life"),
)


class SummaryService:
    def __init__(self, svc: Services):
        self.svc = svc
        self.cfg = svc.cfg.summary

    def _fresh(self, cache: SummaryCache, now: datetime) -> bool:
        if self.cfg.refresh_on_new_day and cache.computed_at.date() != now.date():
            return False
        return now - cache.computed_at < timedelta(minutes=self.cfg.refresh_every_minutes)

    def dynamic(self, identity: AgentIdentity, now: datetime, *, mask: MemoryMask = FULL, force: bool = False, commit_access: bool = True) -> str:
        """The three-aspect summary text (may be empty when no memory is permitted)."""

        state = self.svc.states.get(identity.id)
        cache = state.summaries.get(mask.key)
        if cache is not None and not force and self._fresh(cache, now):
            return cache.text
        aspects: dict[str, str] = {}
        if not mask.empty:
            for key, template in ASPECTS:
                query = template.format(name=identity.name)
                res = self.svc.retriever.retrieve(
                    identity.id,
                    query,
                    now,
                    kinds=mask.kinds,
                    max_items=self.cfg.retrieval_items,
                    budget_tokens=None,
                    commit_access=commit_access,
                    purpose=f"summary:{key}",
                )
                mems = res.delivered
                if not mems:
                    continue
                try:
                    out = self.svc.gateway.run(
                        "summary_aspect",
                        {
                            "aspect_question": query,
                            "statements": bullet(mems),
                            "_statements": [m.description for m in mems],
                            "_name": identity.name,
                            "_aspect": key,
                            "_traits": identity.innate,
                        },
                        agent_id=identity.id,
                        sim_time=now,
                        purpose=f"summary:{key}",
                    )
                    aspects[key] = out.output.summary
                except TaskFailed:
                    continue  # leave the aspect out rather than invent it
        text = "\n".join(aspects[k] for k, _ in ASPECTS if k in aspects)
        state.summaries[mask.key] = SummaryCache(text=text, computed_at=now, mask=mask.key, aspects=aspects, memory_count=self.svc.store.count(identity.id))
        return text

    def description(self, identity: AgentIdentity, now: datetime, *, mask: MemoryMask = FULL, commit_access: bool = True) -> str:
        """[Agent's Summary Description]: static identity + dynamic summary (spec F-1, M-2)."""

        dyn = self.dynamic(identity, now, mask=mask, commit_access=commit_access)
        parts = [identity_block(identity, now)]
        if dyn:
            parts.append(dyn)
        return "\n".join(parts)

    @staticmethod
    def short(identity: AgentIdentity) -> str:
        return short_identity(identity)
