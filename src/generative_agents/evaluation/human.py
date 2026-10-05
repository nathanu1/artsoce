"""Importing genuine human data (paper §6.2–6.3; spec M-5).

Two inputs are supported, both supplied by the researcher as CSV files:

* crowdworker-authored responses (the paper's human baseline: one author per agent who
  watched that agent's replay and memory stream) → condition ``human_crowdworker``;
* believability rankings from human evaluators over a blinded export.

This module only reads and validates. It never writes, simulates or completes a human
condition, and nothing is reported as human evaluation unless such files were imported.
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .stats import Ranking

HUMAN_CONDITION = "human_crowdworker"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def import_human_responses(path: str | Path, *, question_text: dict[str, str], agent_names: dict[str, str]) -> list[dict[str, Any]]:
    """Columns: agent_id, question_id, answer, author_id. Returns response rows."""

    p = Path(path)
    rows = list(csv.DictReader(p.open(newline="")))
    need = {"agent_id", "question_id", "answer", "author_id"}
    if not rows or not need <= set(rows[0]):
        raise ValueError(f"{p} must have columns {sorted(need)}")
    seen: set[tuple[str, str]] = set()
    out = []
    errors = []
    for i, r in enumerate(rows, start=2):
        aid, qid, ans, author = r["agent_id"].strip(), r["question_id"].strip(), (r["answer"] or "").strip(), r["author_id"].strip()
        if aid not in agent_names:
            errors.append(f"line {i}: unknown agent {aid!r}")
        if qid not in question_text:
            errors.append(f"line {i}: unknown question {qid!r}")
        if not ans:
            errors.append(f"line {i}: empty answer")
        if not author:
            errors.append(f"line {i}: missing author_id")
        if (aid, qid) in seen:
            errors.append(f"line {i}: duplicate answer for {aid}/{qid}")
        seen.add((aid, qid))
        out.append(
            {
                "agent_id": aid,
                "agent_name": agent_names.get(aid, aid),
                "condition": HUMAN_CONDITION,
                "question_id": qid,
                "question": question_text.get(qid, ""),
                "answer": ans,
                "author_id": author,
                "source": "human",
                "provenance": {"file": str(p), "sha256": _sha(p)},
            }
        )
    if errors:
        raise ValueError("invalid human responses:\n" + "\n".join(errors[:20]))
    authors = {aid: {r["author_id"] for r in out if r["agent_id"] == aid} for aid in {r["agent_id"] for r in out}}
    multi = {a: sorted(s) for a, s in authors.items() if len(s) > 1}
    for r in out:
        r["provenance"]["authors_for_agent"] = sorted(authors[r["agent_id"]])
        r["provenance"]["one_author_per_agent"] = r["agent_id"] not in multi
    return out


def parse_order(text: str) -> list[str]:
    return [x for x in re.split(r"\s*[>,;\s]\s*", text.strip().upper()) if x]


def import_rankings(path: str | Path, key: dict[str, dict[str, Any]]) -> list[Ranking]:
    """Columns: rater_id, item_id, ranking ("C>A>E>B>D", most believable first)."""

    p = Path(path)
    rows = list(csv.DictReader(p.open(newline="")))
    need = {"rater_id", "item_id", "ranking"}
    if not rows or not need <= set(rows[0]):
        raise ValueError(f"{p} must have columns {sorted(need)}")
    out: list[Ranking] = []
    errors = []
    dup = Counter((r["rater_id"].strip(), r["item_id"].strip()) for r in rows)
    for i, r in enumerate(rows, start=2):
        rater, item = r["rater_id"].strip(), r["item_id"].strip()
        if dup[(rater, item)] > 1:
            errors.append(f"line {i}: rater {rater} ranked item {item} more than once")
            continue
        if item not in key:
            errors.append(f"line {i}: unknown item {item!r}")
            continue
        labels = key[item]["labels"]
        order = parse_order(r["ranking"] or "")
        if sorted(order) != sorted(labels):
            errors.append(f"line {i}: ranking {r['ranking']!r} must order exactly the labels {sorted(labels)}")
            continue
        out.append(Ranking(rater, item, tuple(labels[x] for x in order), key[item].get("agent_id"), key[item].get("question_id")))
    if errors:
        raise ValueError("invalid rankings:\n" + "\n".join(errors[:20]))
    return out
