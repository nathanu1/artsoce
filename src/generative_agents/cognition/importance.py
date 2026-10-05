"""Importance (poignancy) scoring at memory creation (paper §4.1 p. 9; spec D-1 … D-5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..schemas import AgentIdentity
from .context import identity_block

# (mundane examples, poignant examples, label, title)
ANCHORS: dict[str, tuple[str, str, str, str]] = {
    # paper p. 9 (and released poignancy_event_v1.txt)
    "observation": ("brushing teeth, making bed", "a break up, college acceptance", "piece of memory", "Memory"),
    # released poignancy_chat_v1.txt
    "conversation": ("routine morning greetings", "a conversation about breaking up, a fight", "conversation", "Conversation"),
    # released poignancy_thought_v1.txt (used for reflections and plans)
    "thought": ("I need to do the dishes, I need to walk the dog", "I wish to become a professor, I love Elie", "thought", "Thought"),
}


def is_idle_text(text: str) -> bool:
    return text.rstrip(". ").endswith("is idle")


class ImportanceScorer:
    def __init__(self, gateway: Any, *, idle_shortcut: bool = True, batch_statements: bool = True):
        self.gateway = gateway
        self.idle_shortcut = idle_shortcut
        self.batch_statements = batch_statements

    def score(self, identity: AgentIdentity, text: str, kind: str, now: datetime, purpose: str | None = None) -> int:
        if self.idle_shortcut and is_idle_text(text):
            return 1  # released perceive.py:15-17
        mundane, poignant, label, title = ANCHORS[kind]
        result = self.gateway.run(
            "importance",
            {
                "agent_name": identity.name,
                "agent_summary": identity_block(identity, now),
                "mundane_examples": mundane,
                "poignant_examples": poignant,
                "kind_label": label,
                "kind_title": title,
                "memory": text,
                "_memory": text,
                "_kind": kind,
            },
            agent_id=identity.id,
            sim_time=now,
            purpose=purpose or f"importance:{kind}",
        )
        return int(result.output.rating)

    def score_batch(self, identity: AgentIdentity, texts: list[str], now: datetime, purpose: str | None = None) -> list[int]:
        """One call for the statements of a single conversation (spec D-5)."""

        if not texts:
            return []
        if not self.batch_statements:
            return [self.score(identity, t, "conversation", now, purpose) for t in texts]
        items = [(str(i), t) for i, t in enumerate(texts, start=1)]
        expected = {i for i, _ in items}

        def validate(out: Any) -> list[str]:
            got = [r.id for r in out.ratings]
            errs = []
            if set(got) != expected or len(got) != len(expected):
                errs.append(f"need exactly one rating for each id {sorted(expected, key=int)}; got {got}")
            return errs

        result = self.gateway.run(
            "importance_batch",
            {
                "agent_name": identity.name,
                "agent_summary": identity_block(identity, now),
                "numbered_memories": "\n".join(f"{i}. {t}" for i, t in items),
                "_items": items,
            },
            agent_id=identity.id,
            sim_time=now,
            purpose=purpose or "importance:batch",
            validate=validate,
        )
        by_id = {r.id: r.rating for r in result.output.ratings}
        return [int(by_id[i]) for i, _ in items]
