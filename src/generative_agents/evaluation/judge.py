"""Optional LLM judge (spec M-8; prompt §8). EXPLORATORY ONLY.

Each answer is rated 1–7 for plausibility given the character's public description, without
the condition label. The output is written to its own file, labeled ``llm_judge_exploratory``,
summarized descriptively per condition and never turned into TrueSkill "believability" or
presented as human validation.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..config import GAConfig
from ..providers.base import TaskFailed
from ..schemas import AgentIdentity
from ..simulation.runtime import build_runtime

LABEL = "llm_judge_exploratory"


def public_description(ident: AgentIdentity) -> str:
    return f"{ident.name}, age {ident.age}. Traits: {ident.innate}. {ident.learned} {ident.lifestyle}"


def judge_responses(
    responses: list[dict[str, Any]],
    identities: dict[str, AgentIdentity],
    cfg: GAConfig,
    *,
    ledger_path: str | Path | None,
    scope: str,
    provider: Any = None,
) -> dict[str, Any]:
    rt = build_runtime(cfg, store=None, ledger_path=ledger_path, scope=scope, provider=provider, step_getter=lambda: -3)
    rows = []
    for r in responses:
        ident = identities[r["agent_id"]]
        try:
            out = rt.gateway.run(
                "judge",
                {
                    "public_description": public_description(ident),
                    "question": r["question"],
                    "answer": r["answer"],
                    "_answer": r["answer"],
                },
                agent_id=None,
                purpose="evaluation:judge",
            )
            score, why, err = int(out.output.score), out.output.rationale, None
        except TaskFailed as exc:
            score, why, err = None, "", str(exc)
        rows.append(
            {
                "label": LABEL,
                "agent_id": r["agent_id"],
                "question_id": r["question_id"],
                "condition": r["condition"],
                "score": score,
                "rationale": why,
                "error": err,
            }
        )
    by: dict[str, list[int]] = defaultdict(list)
    for x in rows:
        if x["score"] is not None:
            by[x["condition"]].append(x["score"])
    summary = {c: {"n": len(v), "mean": round(statistics.mean(v), 3), "median": statistics.median(v)} for c, v in sorted(by.items())}
    rt.ledger.close()
    return {"label": LABEL, "note": "exploratory automated rating; not human believability", "rows": rows, "summary": summary}
