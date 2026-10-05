"""Appendix B interview questions and placeholder selection (paper pp. 21-22; spec M-3).

Placeholders follow the appendix:

* ``{interacted_1}``, ``{interacted_2}`` (memory questions 1 and 5): two different agents the
  subject has had a conversation with, sampled at random with a recorded seed;
* ``{frequent_1}`` (reflection questions 2-4): the conversation partner with the most
  conversations (ties broken by utterances exchanged, then name; ties are recorded);
* ``{nonexistent_person}``: "Kane Martinez", the paper's non-existent person (checked
  against the population).

When an agent has too few conversation partners, the fallback (agents named in the subject's
own seed memories, then other agents in the population) is recorded with the selection.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..config import repo_path

CATEGORIES = ("self_knowledge", "memory", "plans", "reactions", "reflections")
NONEXISTENT = "Kane Martinez"
PLACEHOLDER = re.compile(r"\{([a-z_0-9]+)\}")


@dataclass(frozen=True)
class Question:
    id: str
    category: str
    text: str
    paper_text: str | None = None

    @property
    def placeholders(self) -> list[str]:
        return PLACEHOLDER.findall(self.text)

    def render(self, bindings: dict[str, str]) -> str:
        missing = [p for p in self.placeholders if p not in bindings]
        if missing:
            raise KeyError(f"question {self.id} needs {missing}")
        return PLACEHOLDER.sub(lambda m: bindings[m.group(1)], self.text)


@dataclass
class QuestionBank:
    name: str
    version: int
    source: str
    questions: list[Question]
    path: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> QuestionBank:
        p = Path(path)
        if not p.is_absolute() and not p.exists():
            p = repo_path(str(path))
        data = yaml.safe_load(p.read_text())
        qs = [Question(q["id"], q["category"], q["text"], q.get("paper_text")) for q in data["questions"]]
        bank = cls(data["name"], int(data.get("version", 1)), data.get("source", ""), qs, str(p), {k: v for k, v in data.items() if k not in ("questions",)})
        bank.validate()
        return bank

    def validate(self) -> None:
        ids = [q.id for q in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate question ids")
        counts = Counter(q.category for q in self.questions)
        unknown = set(counts) - set(CATEGORIES)
        if unknown:
            raise ValueError(f"unknown categories {unknown}")

    def by_id(self, qid: str) -> Question:
        for q in self.questions:
            if q.id == qid:
                return q
        raise KeyError(qid)


@dataclass
class Selection:
    bindings: dict[str, str]
    record: dict[str, Any]


def conversation_partners(db: Any, agent_id: str) -> Counter[str]:
    """Number of conversations per partner, and utterances exchanged, for ``agent_id``."""

    import json

    conv: Counter[str] = Counter()
    utt: Counter[str] = Counter()
    for row in db.query("SELECT json FROM conversations"):
        c = json.loads(row["json"])
        if agent_id not in c["participants"] or not c.get("utterances"):
            continue
        for p in c["participants"]:
            if p != agent_id:
                conv[p] += 1
                utt[p] += len(c["utterances"])
    out: Counter[str] = Counter()
    for p in conv:
        out[p] = conv[p] * 10_000 + utt[p]  # sort key: conversations, then utterances
    return out


def select_placeholders(
    db: Any,
    agent_id: str,
    names: dict[str, str],
    seed_texts: list[str],
    *,
    seed: int,
) -> Selection:
    """Bind the bank's placeholders for one subject agent, recording how each was chosen."""

    rng = random.Random(f"{seed}:{agent_id}")
    others = {a: n for a, n in names.items() if a != agent_id}
    partners = conversation_partners(db, agent_id)
    record: dict[str, Any] = {"seed": seed, "partners": {names.get(p, p): v // 10_000 for p, v in partners.items()}}
    pool = sorted(p for p in partners if p in others)
    source = "conversation_partners"
    if len(pool) < 2:
        seeded = sorted(a for a, n in others.items() if a not in pool and any(n in t or n.split()[0] in t for t in seed_texts))
        pool += seeded
        source = "conversation_partners+seed_mentions" if seeded else source
    if len(pool) < 2:
        rest = sorted(a for a in others if a not in pool)
        pool += rest
        source += "+population"
    picks = rng.sample(pool, k=min(2, len(pool))) if pool else []
    bindings: dict[str, str] = {}
    if picks:
        bindings["interacted_1"] = others[picks[0]]
        bindings["interacted_2"] = others[picks[1] if len(picks) > 1 else picks[0]]
    record["interacted"] = {"source": source, "pool": [others[p] for p in pool], "picked": [others[p] for p in picks]}
    if partners:
        top = max(partners.values())
        tied = sorted(p for p, v in partners.items() if v == top)
        best = tied[0]
        bindings["frequent_1"] = others.get(best, best)
        record["frequent"] = {"source": "most_conversations_then_utterances", "chosen": bindings["frequent_1"], "tied": [others.get(p, p) for p in tied]}
    elif picks:
        bindings["frequent_1"] = others[picks[0]]
        record["frequent"] = {"source": "no_conversations_fallback_to_interacted_1", "chosen": bindings["frequent_1"], "tied": []}
    if NONEXISTENT in names.values():
        raise ValueError(f"{NONEXISTENT} exists in this population; choose another non-existent name")
    bindings["nonexistent_person"] = NONEXISTENT
    return Selection(bindings, record)
