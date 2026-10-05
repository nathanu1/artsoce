"""Recursive reflection (paper §4.2 pp. 9–10; spec E-1 … E-10).

1. Accumulate importance of newly perceived memories since the last successful reflection
   (``Services.remember``; reflections and plans never feed the trigger).
2. Paper mode: reflect when the sum **exceeds** the threshold (150). Compat mode: the
   released countdown from ``importance_trigger_max`` fires at ``<= 0``.
3. Ask for three salient questions over the 100 most recent records.
4. Retrieve for each question; ask for five insights citing the numbered statements.
5. Validate citations (exist, same owner, supplied, acyclic) and store insights as
   reflection memories with evidence edges; depth = 1 + deepest cited memory.
6. Reset the trigger only after at least one insight was stored; otherwise keep it, wait a
   cooldown, and record the failure. Nothing is fabricated.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..memory.evidence import depth_for, has_cycle, validate_evidence
from ..providers.base import TaskFailed
from ..schemas import AgentIdentity, Memory, MemoryKind, MemoryOrigin
from .context import numbered
from .services import Services


class ReflectionEngine:
    def __init__(self, svc: Services):
        self.svc = svc
        self.cfg = svc.cfg.reflection

    @property
    def enabled(self) -> bool:
        return self.svc.cfg.architecture.reflection

    def init_state(self, agent_id: str) -> None:
        state = self.svc.states.get(agent_id)
        if self.cfg.mode == "released_code" and state.reflection_countdown is None:
            state.reflection_countdown = self.cfg.compat_trigger_max

    def should_reflect(self, identity: AgentIdentity, now: datetime) -> bool:
        if not self.enabled:
            return False
        state = self.svc.states.get(identity.id)
        if state.reflection_retry_after is not None and now < state.reflection_retry_after:
            return False
        if self.cfg.mode == "released_code":
            if state.reflection_countdown is None:
                state.reflection_countdown = self.cfg.compat_trigger_max
            return state.reflection_countdown <= 0 and self.svc.store.count(identity.id) > 0
        return state.reflection_accumulator > self.cfg.threshold  # strict ">" (paper p. 10)

    def recent_records(self, identity: AgentIdentity, now: datetime) -> list[Memory]:
        if self.cfg.mode == "released_code":
            state = self.svc.states.get(identity.id)
            mems = [m for m in self.svc.store.for_agent(identity.id, created_before=now) if "idle" not in m.description]
            mems.sort(key=lambda m: (m.last_accessed_at, m.id))
            n = state.reflection_ele_n
            return mems[-n:] if n > 0 else []
        newest = self.svc.store.for_agent(identity.id, created_before=now, limit=self.cfg.recent_records, newest_first=True)
        return list(reversed(newest))

    def run(self, identity: AgentIdentity, now: datetime) -> dict[str, Any]:
        svc = self.svc
        state = svc.states.get(identity.id)
        batch_id = f"{identity.id}.r{state.reflections_done + 1:04d}"
        report: dict[str, Any] = {"batch_id": batch_id, "questions": [], "insights": [], "failures": [], "trigger": self._trigger_snapshot(state)}
        records = self.recent_records(identity, now)
        if not records:
            report["failures"].append("no recent records")
            self._fail(state, now)
            svc.events.log("reflection", now, identity.id, **report)
            return report
        n_q = self.cfg.questions
        try:
            q_out = svc.gateway.run(
                "reflection_questions",
                {
                    "statements": "\n".join(m.description for m in records),
                    "n": str(n_q),
                    "_statements": [m.description for m in records],
                    "_n": n_q,
                    "_name": identity.name,
                },
                agent_id=identity.id,
                sim_time=now,
                purpose="reflection:questions",
                validate=lambda o: [] if len(o.questions) == n_q and all(q.strip() for q in o.questions) else [f"need exactly {n_q} non-empty questions"],
            )
            questions = [q.strip() for q in q_out.output.questions]
        except TaskFailed as exc:
            report["failures"].append(f"questions: {exc}")
            self._fail(state, now)
            svc.events.log("reflection", now, identity.id, **report)
            return report

        # Retrieve evidence for every question before storing any insight, as the released
        # code does (reflect.py:110-131), so insights in one batch never cite each other.
        retrieved: list[tuple[str, Any, list[Memory]]] = []
        for question in questions:
            res = svc.retriever.retrieve(identity.id, question, now, max_items=self.cfg.retrieval_items, budget_tokens=None, purpose="reflection:evidence")
            retrieved.append((question, res.trace_id, res.delivered))

        stored: list[Memory] = []
        for question, trace_id, supplied in retrieved:
            entry: dict[str, Any] = {"question": question, "trace_id": trace_id, "supplied": [m.id for m in supplied], "insight_ids": []}
            report["questions"].append(entry)
            if not supplied:
                entry["skipped"] = "no memories retrieved"
                continue
            text, handles = numbered(supplied)
            n_i = self.cfg.insights_per_question

            def validate(out: Any, handles: dict[str, str] = handles, n_i: int = n_i) -> list[str]:
                errs = []
                if not out.insights:
                    errs.append("give at least one insight")
                if len(out.insights) > n_i:
                    errs.append(f"give at most {n_i} insights")
                for k, ins in enumerate(out.insights, start=1):
                    if not ins.insight.strip():
                        errs.append(f"insight {k} is empty")
                    if not ins.evidence:
                        errs.append(f"insight {k} cites no statements")
                    bad = [h for h in ins.evidence if h.strip().strip(".") not in handles]
                    if bad:
                        errs.append(f"insight {k} cites numbers that were not shown: {bad}")
                return errs

            try:
                out = svc.gateway.run(
                    "reflection_insights",
                    {
                        "agent_name": identity.name,
                        "numbered_statements": text,
                        "n": str(n_i),
                        "_items": [(h, svc.store.get(mid).description) for h, mid in handles.items()],
                        "_n": n_i,
                        "_name": identity.name,
                    },
                    agent_id=identity.id,
                    sim_time=now,
                    purpose="reflection:insights",
                    validate=validate,
                )
            except TaskFailed as exc:
                entry["failure"] = str(exc)
                report["failures"].append(f"insights for {question!r}: {exc}")
                continue
            supplied_ids = {m.id for m in supplied}
            for ins in out.output.insights:
                evidence_ids = list(dict.fromkeys(handles[h.strip().strip(".")] for h in ins.evidence))
                errors = validate_evidence(svc.store, identity.id, evidence_ids, supplied_ids)
                if errors:
                    report["failures"].append(f"rejected insight {ins.insight!r}: {errors}")
                    continue
                mem = svc.remember(
                    identity,
                    ins.insight.strip(),
                    MemoryKind.REFLECTION,
                    MemoryOrigin.INFERENCE,
                    now,
                    importance_kind="thought",
                    evidence_ids=evidence_ids,
                    depth=depth_for(svc.store, evidence_ids),
                    metadata={"question": question, "batch_id": batch_id, "call_ids": out.call_ids},
                )
                if has_cycle(svc.store, mem.id):  # impossible by construction; checked anyway
                    report["failures"].append(f"cycle detected at {mem.id}")
                stored.append(mem)
                entry["insight_ids"].append(mem.id)
                report["insights"].append({"id": mem.id, "text": mem.description, "evidence": evidence_ids, "depth": mem.depth})
        if stored:
            self._reset(state, now)
        else:
            self._fail(state, now)
        report["stored"] = len(stored)
        svc.events.log("reflection", now, identity.id, **report)
        return report

    # ------------------------------------------------------------------ trigger bookkeeping
    def _trigger_snapshot(self, state: Any) -> dict[str, Any]:
        return {
            "mode": self.cfg.mode,
            "accumulator": state.reflection_accumulator,
            "threshold": self.cfg.threshold,
            "countdown": state.reflection_countdown,
            "ele_n": state.reflection_ele_n,
        }

    def _reset(self, state: Any, now: datetime) -> None:
        state.reflection_accumulator = 0.0
        state.reflection_ele_n = 0
        if self.cfg.mode == "released_code":
            state.reflection_countdown = self.cfg.compat_trigger_max
        state.last_reflection_at = now
        state.reflection_retry_after = None
        state.reflections_done += 1

    def _fail(self, state: Any, now: datetime) -> None:
        state.reflection_retry_after = now + timedelta(minutes=self.cfg.retry_cooldown_minutes)
        state.failures += 1
