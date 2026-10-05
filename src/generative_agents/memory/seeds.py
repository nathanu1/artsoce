"""Seed memories from the authored history statements (paper p. 5; spec A-2, A-3).

``verbatim`` (default): each semicolon-delimited phrase is entered as one memory, unchanged.
``inner_thought_llm`` (released code, converse.py:239-254): each phrase is first rewritten by
the model into a statement about the agent; the original phrase is kept in metadata.

Seeds are typed as observations with ``origin=seed`` and ``seed=True``. Their importance is
rated with the observation anchors (the released code rates the original phrase as an event)
and they do not feed the reflection trigger (the released ``add_thought`` leaves the trigger
untouched).
"""

from __future__ import annotations

from datetime import datetime

from ..cognition.services import Services
from ..providers.base import TaskFailed
from ..schemas import Memory, MemoryKind, MemoryOrigin


def seed_agent(svc: Services, spec, now: datetime, rendering: str = "verbatim") -> list[Memory]:
    identity = spec.identity
    existing = svc.db.one("SELECT COUNT(*) AS n FROM memories WHERE owner_id=? AND seed=1", (identity.id,))
    if existing and int(existing["n"]) > 0:
        raise RuntimeError(f"{identity.id} already has seed memories; refusing to import them twice (spec A-4)")
    texts: list[str] = []
    meta: list[dict] = []
    for s in spec.seeds:
        text = s.text.strip()
        m = {"seed_index": s.index, "flags": s.flags, "rendering": rendering}
        if rendering == "inner_thought_llm":
            try:
                out = svc.gateway.run(
                    "seed_thought",
                    {"agent_name": identity.name, "thought": text, "_name": identity.name, "_thought": text},
                    agent_id=identity.id,
                    sim_time=now,
                    purpose="seed:render",
                )
                m["original"] = text
                text = out.output.statement.strip()
            except TaskFailed as exc:
                m["render_failed"] = str(exc)  # keep the authored phrase rather than invent one
        texts.append(text)
        meta.append(m)
    originals = [mm.get("original", t) for mm, t in zip(meta, texts, strict=True)]
    scores = svc.importance.score_batch(identity, originals, now, purpose="importance:seed", kind="observation") if texts else []
    out: list[Memory] = []
    for text, m, score in zip(texts, meta, scores, strict=True):
        out.append(svc.remember(identity, text, MemoryKind.OBSERVATION, MemoryOrigin.SEED, now, importance=score, seed=True, metadata=m))
    return out
