"""Per-task input/output examples drawn from recorded call ledgers (build prompt §2).

For every template in ``prompts/`` this writes one Markdown file: where the template comes
from, what information it may see, its output schema, and the smallest successful call
recorded for that task, shown exactly as sent (system and user text) and received (raw and
validated output). When a run repaired an output for that task, the smallest repaired
exchange is shown too, so the validator's message and the corrected answer can be read
together. An index lists every task with its call counts and the run its example came from.

Several runs can be given; each task's example comes from the first run that has a
successful call made with the current version of its template. Examples are only as
informative as the run they come from: a mock run's inputs are exactly what a model would be
sent in that state, but its outputs show the format, not model behavior. Every page names
its run and mode.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import GAConfig
from .prompting import PromptRegistry, PromptTemplate
from .providers.schema import strict_json_schema

FAILED = ("error", "refusal", "truncated")


@dataclass
class Source:
    run_dir: Path
    run_id: str
    mode: str
    label: str
    rows: dict[str, list[dict[str, Any]]]
    differs: list[str]

    @property
    def title(self) -> str:
        parts = [] if self.mode.upper() in self.label.upper() else [self.mode.upper()]
        return f"run `{self.run_id}` ({', '.join([*parts, self.label] if self.label else parts)})"

    @property
    def settings(self) -> str:
        return "settings that differ from the defaults: " + ", ".join(f"`{d}`" for d in self.differs) if self.differs else "default architecture settings"


def _differs(fidelity: list[dict[str, Any]]) -> list[str]:
    defaults = {row["setting"]: row["value"] for row in json.loads(json.dumps(GAConfig().fidelity_table(), default=str))}
    return [f"{row['setting']}={row['value']}" for row in fidelity if row["setting"] in defaults and row["value"] != defaults[row["setting"]]]


def load_source(run_dir: str | Path) -> Source:
    run_dir = Path(run_dir)
    ledger = run_dir / "provider.sqlite"
    if not ledger.exists():
        raise FileNotFoundError(f"{ledger} not found")
    manifest = json.loads((run_dir / "manifest.json").read_text()) if (run_dir / "manifest.json").exists() else {}
    conn = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in conn.execute("SELECT * FROM calls ORDER BY id"):
        by_task[r["task"]].append(dict(r))
    conn.close()
    return Source(
        run_dir,
        str(manifest.get("run_id") or run_dir.name),
        str(manifest.get("mode") or "unknown"),
        str(manifest.get("label") or ""),
        by_task,
        _differs(manifest.get("fidelity") or []),
    )


def _size(row: dict[str, Any]) -> int:
    return len(row["system"]) + len(row["prompt"]) + len(row.get("raw_output") or "")


def _smallest(rows: list[dict[str, Any]], **match: Any) -> dict[str, Any] | None:
    hits = [r for r in rows if all(r.get(k) == v for k, v in match.items())]
    return min(hits, key=lambda r: (_size(r), r["id"])) if hits else None


def _previous_attempt(rows: list[dict[str, Any]], repair: dict[str, Any]) -> dict[str, Any] | None:
    earlier = [r for r in rows if r["id"] < repair["id"] and r["scope"] == repair["scope"] and r["agent_id"] == repair["agent_id"] and r["status"] == "invalid"]
    return earlier[-1] if earlier else None


def _fence(text: str | None, lang: str = "text") -> list[str]:
    body = (text or "").rstrip("\n")
    fence = "````" if "```" in body else "```"
    return [f"{fence}{lang}", body, fence]


def _pretty(text: str | None) -> str:
    try:
        return json.dumps(json.loads(text or ""), indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return text or ""


def _call_lines(row: dict[str, Any]) -> list[str]:
    tokens = f"{row['input_tokens']} in / {row['output_tokens']} out" + (" (estimated)" if row.get("tokens_estimated") else "")
    lines = [
        f"Ledger call {row['id']} · scope `{row['scope']}` · sim time {row['sim_time'] or 'n/a'} · agent `{row['agent_id'] or 'n/a'}`"
        f" · model `{row['model']}` · status `{row['status']}` · tokens {tokens}",
        "",
        "**System**",
        "",
        *_fence(row["system"]),
        "",
        "**User**",
        "",
        *_fence(row["prompt"]),
        "",
        "**Raw output**",
        "",
        *_fence(row.get("raw_output") or row.get("error"), "json" if row.get("raw_output") else "text"),
    ]
    if row.get("parsed_json"):
        lines += ["", "**Validated output**", "", *_fence(_pretty(row["parsed_json"]), "json")]
    return lines


def _current(rows: list[dict[str, Any]], tpl: PromptTemplate) -> list[dict[str, Any]]:
    return [r for r in rows if r["template_hash"] == tpl.sha256]


def _task_page(tpl: PromptTemplate, source: Source | None, out: Path) -> str:
    rows = _current(source.rows.get(tpl.id, []), tpl) if source else []
    counts = Counter(r["status"] for r in rows)
    repairs = sum(1 for r in rows if r.get("attempt_kind") == "repair")
    link = Path(os.path.relpath(tpl.path, out)).as_posix()
    lines = [f"# `{tpl.template_id}`", ""]
    if source is not None:
        what = "show the format only, not model behavior" if source.mode != "live" else "are as received"
        lines += [f"> Example from {source.title}, {source.settings}. Inputs are exactly what the model was sent in that state; outputs {what}.", ""]
    lines += [
        f"* Template: [`prompts/{tpl.path.name}`]({link}) · SHA-256 `{tpl.sha256}`",
        f"* Source: {tpl.source}",
        f"* Information scope: {tpl.scope}",
        f"* Output model: `{tpl.output_model.__name__}` · max output tokens {tpl.max_output_tokens} · effort {tpl.effort or 'default'}",
    ]
    if source is not None:
        lines.append(
            f"* Calls in this run: {len(rows)} ("
            + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
            + f"; {repairs} repair attempt{'s' if repairs != 1 else ''})"
        )
    lines += ["", "## Output schema", "", *_fence(json.dumps(strict_json_schema(tpl.output_model), indent=2), "json"), ""]
    ok = _smallest(rows, status="ok", attempt_kind="initial") or _smallest(rows, status="ok")
    if ok is None:
        lines += ["## Example", "", "No successful call with this version of the template is recorded in the given runs.", ""]
    else:
        lines += ["## Smallest successful call", "", *_call_lines(ok), ""]
    repaired = _smallest(rows, status="ok", attempt_kind="repair")
    if repaired is not None:
        first = _previous_attempt(rows, repaired)
        lines += ["## A repaired call", ""]
        if first is not None:
            errors = "\n".join(json.loads(first["validation_errors"] or "[]")) or "(no message recorded)"
            lines += [f"Ledger call {first['id']} was rejected by the validator:", "", *_fence(errors), ""]
        lines += ["The repair request repeats the prompt with the validator's message and the previous answer appended:", "", *_call_lines(repaired), ""]
    elif ok is not None:
        lines += ["No call for this task needed a repair in this run.", ""]
    failed = [r for r in rows if r["status"] in FAILED]
    if failed:
        lines += ["## Failed calls", ""] + [f"* call {r['id']} (`{r['scope']}`): {r['status']} — {(r.get('error') or '')[:200]}" for r in failed[:5]] + [""]
    if source is not None:
        stale = len(source.rows.get(tpl.id, [])) - len(rows)
        if stale:
            lines += [
                f"_{stale} call{'s' if stale != 1 else ''} recorded with an earlier version of this template {'are' if stale != 1 else 'is'} not shown._",
                "",
            ]
    return "\n".join(lines)


def write_prompt_examples(run_dirs: str | Path | list[str | Path], out_dir: str | Path | None = None, registry: PromptRegistry | None = None) -> dict[str, Any]:
    dirs = [run_dirs] if isinstance(run_dirs, str | Path) else list(run_dirs)
    if not dirs:
        raise ValueError("at least one run directory is required")
    sources = [load_source(d) for d in dirs]
    out = Path(out_dir) if out_dir else Path(dirs[0]) / "exports" / "prompt_examples"
    out.mkdir(parents=True, exist_ok=True)
    registry = registry or PromptRegistry()
    index = [
        "# Prompt examples",
        "",
        "One file per task, generated by `ga prompt-examples`. Each shows the template's source and",
        "information scope, its output schema and the smallest successful call recorded for the task:",
        "system and user text exactly as sent, raw and validated output. Repaired calls are shown when",
        "the run had one.",
        "",
        "Source runs (each task's example comes from the first run that has one):",
        "",
        *[f"* {s.title}; {s.settings}" for s in sources],
        "",
    ]
    modes = sorted({s.mode for s in sources} - {"live"})
    if modes:
        index += [
            f"> **{' + '.join(m.upper() for m in modes)} OUTPUTS.** The inputs are what a model is sent in that state; the",
            "> outputs show the expected format only and are not evidence of how a model behaves.",
            "",
        ]
    index += [
        "| Task | Template | Output model | Example from | Calls | ok | invalid | failed |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    written: dict[str, str | None] = {}
    for task in registry.tasks():
        tpl = registry.get(task)
        with_ok = [s for s in sources if any(r["status"] == "ok" for r in _current(s.rows.get(task, []), tpl))]
        with_any = [s for s in sources if _current(s.rows.get(task, []), tpl)]
        source = (with_ok or with_any or [None])[0]
        (out / f"{task}.md").write_text(_task_page(tpl, source, out))
        rows = _current(source.rows.get(task, []), tpl) if source else []
        c = Counter(r["status"] for r in rows)
        failed = sum(c[s] for s in FAILED)
        index.append(
            f"| [{task}]({task}.md) | `{tpl.template_id}` | `{tpl.output_model.__name__}` | {f'`{source.run_id}`' if source else '—'} "
            f"| {len(rows)} | {c['ok']} | {c['invalid']} | {failed} |"
        )
        written[task] = source.run_id if source and with_ok else None
    index += ["", "Regenerate after changing a template: re-run the producing commands, then `ga prompt-examples --run-dir DIR ... --out DIR`.", ""]
    (out / "README.md").write_text("\n".join(index))
    return {"dir": str(out), "tasks": written, "without_examples": sorted(t for t, s in written.items() if s is None)}
