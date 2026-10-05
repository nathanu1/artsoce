"""Blinded, randomized exports for human ranking (paper §6.1–6.4; spec M-5).

For every (agent, question) the answers of all conditions become one rating item. Answers
are shuffled with a recorded seed and shown under letters A, B, C, …; the letter → condition
key is written to a separate file that must not be given to raters. A rubric and per-agent
context (identity and where to replay the run) are exported next to the form, so raters can
review the agent's history the way the paper's evaluators watched a replay.
"""

from __future__ import annotations

import csv
import json
import random
import string
from collections import defaultdict
from pathlib import Path
from typing import Any

RUBRIC = """# Believability rating rubric

You will see one question asked to a character in a simulated town and several answers,
labeled with letters. The answers come from different sources; you are not told which.

For each item, rank all answers from **most believable** to **least believable**:
*how likely is it that this character, given who they are and what has happened to them in
the replay you watched, would give this answer?*

* Judge believability for this specific character, not writing quality.
* A short answer can be very believable; a fluent one can contradict the character's history.
* Rank every answer exactly once. Write the ranking as letters, best first, e.g. `C>A>E>B>D`.

These are simulated characters. Plausibility here says nothing about real people.
"""


def blinded_export(
    responses: list[dict[str, Any]], out_dir: str | Path, *, seed: int, run_info: dict[str, Any] | None = None, identities: dict[str, Any] | None = None
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in responses:
        groups[(r["agent_id"], r["question_id"])].append(r)
    items, key, form = [], {}, []
    for n, ((aid, qid), group) in enumerate(sorted(groups.items()), start=1):
        conds = [g["condition"] for g in group]
        if len(set(conds)) != len(conds):
            raise ValueError(f"two answers from the same condition for {aid}/{qid}")
        shuffled = rng.sample(group, len(group))
        item_id = f"i{n:04d}"
        labels = {}
        for letter, g in zip(string.ascii_uppercase, shuffled, strict=False):
            labels[letter] = g["condition"]
            items.append({"item_id": item_id, "agent_name": g["agent_name"], "question": g["question"], "label": letter, "answer": g["answer"]})
        key[item_id] = {"agent_id": aid, "question_id": qid, "labels": labels}
        form.append(
            {"item_id": item_id, "agent_name": shuffled[0]["agent_name"], "question": shuffled[0]["question"], "labels": "".join(labels), "ranking": ""}
        )
    with (out / "rating_items.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["item_id", "agent_name", "question", "label", "answer"])
        w.writeheader()
        w.writerows(items)
    with (out / "rating_form.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["rater_id", "item_id", "agent_name", "question", "labels", "ranking"])
        w.writeheader()
        for row in form:
            w.writerow({"rater_id": "", **row})
    (out / "blinding_key.json").write_text(json.dumps({"seed": seed, "do_not_share_with_raters": True, "items": key}, indent=2))
    (out / "rubric.md").write_text(RUBRIC)
    ctx = out / "context"
    ctx.mkdir(exist_ok=True)
    for aid in sorted({r["agent_id"] for r in responses}):
        ident = (identities or {}).get(aid)
        lines = [f"# {ident.name if ident else aid}", ""]
        if ident is not None:
            lines += [f"* Age: {ident.age}", f"* Traits: {ident.innate}", f"* Background: {ident.learned}", f"* Lifestyle: {ident.lifestyle}", ""]
        if run_info:
            lines += [f"Replay: `ga serve --run-dir {run_info.get('run_dir', '')}` and select this character.", f"Snapshot: {run_info.get('snapshot', '')}", ""]
        (ctx / f"{aid}.md").write_text("\n".join(lines))
    return {"dir": str(out), "items": len(key), "answers": len(items), "seed": seed}


def load_key(path: str | Path) -> dict[str, dict[str, Any]]:
    data = json.loads(Path(path).read_text())
    return data["items"]
