"""Hierarchical planning (paper §4.3 p. 11, Appendix A p. 21; spec G-1 … G-8).

1. **Day plan.** At the start of each simulated day the agent drafts its day "in broad
   strokes" (5–8 items) from its identity, its dynamic summary and a summary of its previous
   day. The plan is stored in the agent's memory stream.
2. **Hour blocks.** The broad plan becomes an hour-by-hour schedule that covers 00:00–24:00
   with no gaps or overlaps (validated).
3. **Tasks, just in time.** The hour-long window of the current block is decomposed into
   5–15 minute tasks only when the agent reaches it. Sleep is not decomposed; windows no
   longer than one task are used as they are (no call).
4. **Replanning.** An unplanned activity (reaction, wait, conversation) is inserted at the
   current minute; overlapping tasks are superseded and the rest of the window is
   regenerated from the end of the inserted activity (§4.3.1).

Every generated level is validated; invalid output gets one repair attempt. When a day plan
or schedule cannot be produced, the agent has no plan (it idles and the failure is logged and
retried after a cooldown) rather than receiving an invented one. When only a decomposition
fails, the agent follows its own hour-level activity for that window and the fallback is
recorded on the task.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from ..db import Database, iso, parse_iso
from ..providers.base import TaskFailed
from ..schemas import AgentIdentity, MemoryKind, MemoryOrigin, PlanItem, PlanLevel, PlanStatus
from ..simulation.clock import day_label, hhmm, long_time, parse_hhmm
from .services import Services
from .summary import SummaryService

SLEEP_RE = re.compile(r"\b(sleep|sleeping|asleep|nap|napping|in bed|go(es|ing)? to bed|bedtime)\b", re.I)
HHMM_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")


def is_sleep(activity: str) -> bool:
    return bool(SLEEP_RE.search(activity or ""))


def floor_minute(t: datetime) -> datetime:
    return t.replace(second=0, microsecond=0)


def _hm(text: str) -> int | None:
    m = HHMM_RE.match(text or "")
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if mi >= 60 or h > 24 or (h == 24 and mi != 0):
        return None
    return h * 60 + mi


def _day_start(d: date) -> datetime:
    return datetime(d.year, d.month, d.day)


class PlanStore:
    """Plan items in the ``plans`` table (one row per item, JSON payload)."""

    def __init__(self, db: Database):
        self.db = db
        self._counters: dict[str, int] = {}

    def invalidate(self) -> None:
        self._counters.clear()

    def next_id(self, agent_id: str) -> str:
        if agent_id not in self._counters:
            row = self.db.one("SELECT COUNT(*) AS n FROM plans WHERE agent_id=?", (agent_id,))
            self._counters[agent_id] = int(row["n"]) if row else 0
        self._counters[agent_id] += 1
        return f"{agent_id}.p{self._counters[agent_id]:05d}"

    def save(self, item: PlanItem) -> PlanItem:
        self.db.execute(
            """INSERT INTO plans(id, agent_id, level, parent_id, day, start, duration_min, status, json)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET status=excluded.status, duration_min=excluded.duration_min, json=excluded.json""",
            (
                item.id,
                item.agent_id,
                item.level.value,
                item.parent_id,
                item.day,
                iso(item.start),
                item.duration_min,
                item.status.value,
                item.model_dump_json(),
            ),
        )
        return item

    def new(self, agent_id: str, level: PlanLevel, start: datetime, duration_min: int, description: str, now: datetime, **kw: Any) -> PlanItem:
        item = PlanItem(
            id=self.next_id(agent_id),
            agent_id=agent_id,
            level=level,
            start=start,
            duration_min=duration_min,
            description=description,
            created_at=now,
            day=kw.pop("day", start.date().isoformat()),
            **kw,
        )
        return self.save(item)

    def get(self, item_id: str) -> PlanItem | None:
        row = self.db.one("SELECT json FROM plans WHERE id=?", (item_id,))
        return PlanItem.model_validate_json(row["json"]) if row else None

    def items(self, agent_id: str, *, day: str | None = None, level: PlanLevel | None = None, active_only: bool = True) -> list[PlanItem]:
        sql = "SELECT json FROM plans WHERE agent_id=?"
        params: list[Any] = [agent_id]
        if day is not None:
            sql += " AND day=?"
            params.append(day)
        if level is not None:
            sql += " AND level=?"
            params.append(level.value)
        if active_only:
            sql += " AND status NOT IN (?, ?)"
            params += [PlanStatus.SUPERSEDED.value, PlanStatus.FAILED.value]
        sql += " ORDER BY start, id"
        return [PlanItem.model_validate_json(r["json"]) for r in self.db.query(sql, tuple(params))]

    def overlapping(self, agent_id: str, level: PlanLevel, t0: datetime, t1: datetime) -> list[PlanItem]:
        """Active items of ``level`` that overlap [t0, t1)."""

        rows = self.db.query(
            """SELECT json FROM plans WHERE agent_id=? AND level=? AND status NOT IN (?, ?)
               AND start < ? ORDER BY start, id""",
            (agent_id, level.value, PlanStatus.SUPERSEDED.value, PlanStatus.FAILED.value, iso(t1)),
        )
        out = []
        for r in rows:
            it = PlanItem.model_validate_json(r["json"])
            if it.end > t0:
                out.append(it)
        return out

    def at(self, agent_id: str, level: PlanLevel, t: datetime) -> PlanItem | None:
        """The active item containing ``t`` (the most recently created wins)."""

        hits = [it for it in self.overlapping(agent_id, level, t, t + timedelta(microseconds=1)) if it.status != PlanStatus.DONE]
        if not hits:
            return None
        return max(hits, key=lambda it: (it.created_at, it.id))

    def set_status(self, item: PlanItem, status: PlanStatus, **meta: Any) -> PlanItem:
        item.status = status
        item.metadata.update(meta)
        return self.save(item)


class Planner:
    def __init__(self, svc: Services, summary: SummaryService, plans: PlanStore):
        self.svc = svc
        self.summary = summary
        self.plans = plans
        self.cfg = svc.cfg.planning

    @property
    def enabled(self) -> bool:
        return self.svc.cfg.architecture.planning

    # ------------------------------------------------------------------ day level
    def has_day(self, agent_id: str, d: date) -> bool:
        return bool(self.plans.items(agent_id, day=d.isoformat(), level=PlanLevel.HOUR))

    def ensure_day(self, identity: AgentIdentity, now: datetime) -> bool:
        """Create today's plan if missing. Returns True when a plan exists afterwards."""

        today = now.date()
        if self.has_day(identity.id, today):
            return True
        state = self.svc.states.get(identity.id)
        retry = state.extra.get("plan_retry_after")
        if retry and now < parse_iso(retry):
            return False
        try:
            self._make_day(identity, now)
        except TaskFailed as exc:
            state.extra["plan_retry_after"] = iso(now + timedelta(minutes=30))
            state.failures += 1
            self.svc.events.log("plan_failure", now, identity.id, level="day", error=str(exc), errors=exc.errors[:5])
            return False
        state.extra.pop("plan_retry_after", None)
        state.plan_day = today.isoformat()
        return True

    def plan_summary(self, identity: AgentIdentity, now: datetime) -> str:
        dyn = self.summary.dynamic(identity, now)
        return "\n".join(p for p in (identity.learned, identity.currently, dyn) if p)

    def previous_day(self, identity: AgentIdentity, now: datetime) -> str | None:
        """Summary of the previous day from the agent's own memories (released revise_identity)."""

        if not self.svc.store.count(identity.id):
            return None
        yesterday = now - timedelta(days=1)
        queries = [f"{identity.name}'s plan for {day_label(yesterday)}.", f"Important recent events for {identity.name}'s life."]
        mems = self.svc.retriever.retrieve_many(identity.id, queries, now, max_items=15, budget_tokens=None, purpose="plan:previous_day")
        if not mems:
            return None
        out = self.svc.gateway.run(
            "previous_day",
            {
                "statements": "\n".join(f"- {m.description}" for m in mems),
                "agent_name": identity.name,
                "first_name": identity.first_name,
                "yesterday_label": day_label(yesterday),
                "today_label": day_label(now),
                "_statements": [m.description for m in mems],
                "_name": identity.name,
                "_yesterday": day_label(yesterday),
            },
            agent_id=identity.id,
            sim_time=now,
            purpose="plan:previous_day",
        )
        return out.output.summary.strip()

    def _make_day(self, identity: AgentIdentity, now: datetime) -> None:
        svc = self.svc
        state = svc.states.get(identity.id)
        today = now.date()
        prev = None
        if state.plan_day is not None and state.plan_day != today.isoformat():
            try:
                prev = self.previous_day(identity, now)
            except TaskFailed as exc:
                svc.events.log("plan_failure", now, identity.id, level="previous_day", error=str(exc))
            state.previous_day_summary = prev
        summary = self.plan_summary(identity, now)
        lo, hi = self.cfg.day_chunks_min, self.cfg.day_chunks_max
        prev_text = f"Summary of {identity.first_name}'s previous day: {prev}" if prev else ""

        def validate_day(out: Any) -> list[str]:
            errs = []
            if _hm(out.wake_up_time) is None:
                errs.append("wake_up_time must be HH:MM (24-hour)")
            if not (lo <= len(out.items) <= hi):
                errs.append(f"give between {lo} and {hi} items (got {len(out.items)})")
            last = -1
            for k, it in enumerate(out.items, start=1):
                t = _hm(it.time)
                if t is None or t >= 24 * 60:
                    errs.append(f"item {k}: time {it.time!r} is not HH:MM between 00:00 and 23:59")
                    continue
                if t <= last:
                    errs.append(f"item {k}: times must be in increasing order")
                last = t
                if not it.activity.strip():
                    errs.append(f"item {k}: empty activity")
            return errs

        day = svc.gateway.run(
            "day_plan",
            {
                "agent_name": identity.name,
                "age": str(identity.age),
                "traits": identity.innate,
                "agent_summary": summary,
                "lifestyle": identity.lifestyle,
                "daily_requirement": identity.daily_plan_req or "",
                "previous_day": prev_text,
                "day_label": day_label(now),
                "first_name": identity.first_name,
                "min_items": str(lo),
                "max_items": str(hi),
                "_identity": identity.model_dump(),
                "_knowledge": "\n".join([summary, prev or ""]),
                "_day_label": day_label(now),
                "_min_items": lo,
                "_max_items": hi,
            },
            agent_id=identity.id,
            sim_time=now,
            purpose="plan:day",
            validate=validate_day,
        )
        items = [(_hm(it.time) or 0, it.activity.strip()) for it in day.output.items]
        wake = day.output.wake_up_time
        broad = "; ".join(f"{hhmm(_day_start(today) + timedelta(minutes=m))} {a}" for m, a in items)
        plan_text = f"This is {identity.name}'s plan for {day_label(now)}: wake up at {wake}; {broad}."
        day_mem = svc.remember(
            identity, plan_text, MemoryKind.PLAN, MemoryOrigin.INTENTION, now, importance_kind="thought", metadata={"level": "day", "call_ids": day.call_ids}
        )
        self.plans.new(
            identity.id,
            PlanLevel.DAY,
            _day_start(today),
            24 * 60,
            plan_text,
            now,
            source="generated",
            memory_id=day_mem.id,
            metadata={"wake_up_time": wake, "items": [{"minute": m, "activity": a} for m, a in items], "call_ids": day.call_ids},
        )

        def validate_hours(out: Any) -> list[str]:
            errs = []
            if not out.blocks:
                return ["give at least one block"]
            cursor = 0
            for k, b in enumerate(out.blocks, start=1):
                s, e = _hm(b.start), _hm(b.end)
                if s is None or e is None:
                    errs.append(f"block {k}: start and end must be HH:MM")
                    continue
                if s != cursor:
                    errs.append(f"block {k} starts at {b.start} but the previous block ended at {cursor // 60:02d}:{cursor % 60:02d}")
                if e <= s:
                    errs.append(f"block {k} must end after it starts")
                if not b.activity.strip():
                    errs.append(f"block {k}: empty activity")
                cursor = e if e is not None else cursor
            if cursor != 24 * 60:
                errs.append("the last block must end at 24:00")
            return errs

        day_lines = "\n".join(f"{hhmm(_day_start(today) + timedelta(minutes=m))} {a}" for m, a in items)
        hours = svc.gateway.run(
            "hourly_schedule",
            {
                "agent_name": identity.name,
                "age": str(identity.age),
                "traits": identity.innate,
                "agent_summary": summary,
                "lifestyle": identity.lifestyle,
                "day_label": day_label(now),
                "first_name": identity.first_name,
                "day_plan": day_lines,
                "wake_up_time": wake,
                "_items": items,
            },
            agent_id=identity.id,
            sim_time=now,
            purpose="plan:hourly",
            validate=validate_hours,
        )
        blocks: list[tuple[int, int, str]] = []
        for b in hours.output.blocks:
            s, e, a = _hm(b.start) or 0, _hm(b.end) or 0, b.activity.strip()
            if blocks and blocks[-1][2] == a and blocks[-1][1] == s:
                blocks[-1] = (blocks[-1][0], e, a)  # merge identical neighbours
            else:
                blocks.append((s, e, a))
        created: list[PlanItem] = []
        for s, e, a in blocks:
            created.append(
                self.plans.new(
                    identity.id,
                    PlanLevel.HOUR,
                    _day_start(today) + timedelta(minutes=s),
                    e - s,
                    a,
                    now,
                    source="generated",
                    metadata={"call_ids": hours.call_ids},
                )
            )
        if self.cfg.store_hourly_in_memory and created:
            texts = [
                f"{identity.name} plans to {it.description} from {hhmm(it.start)} to {hhmm(it.end) if it.end.date() == today else '24:00'} on {day_label(now)}."
                for it in created
            ]
            scores = svc.importance.score_batch(identity, texts, now, purpose="importance:plan", kind="thought")
            for it, text, score in zip(created, texts, scores, strict=True):
                mem = svc.remember(identity, text, MemoryKind.PLAN, MemoryOrigin.INTENTION, now, importance=score, plan_id=it.id, metadata={"level": "hour"})
                it.memory_id = mem.id
                self.plans.save(it)
        svc.events.log(
            "day_plan",
            now,
            identity.id,
            day=today.isoformat(),
            wake_up_time=wake,
            items=[{"time": hhmm(_day_start(today) + timedelta(minutes=m)), "activity": a} for m, a in items],
            blocks=[{"start": f"{s // 60:02d}:{s % 60:02d}", "end": f"{e // 60:02d}:{e % 60:02d}", "activity": a} for s, e, a in blocks],
            previous_day=prev,
        )

    # ------------------------------------------------------------------ task level (JIT)
    def window_of(self, block: PlanItem, t: datetime) -> tuple[datetime, datetime]:
        if is_sleep(block.description):
            return block.start, block.end
        span = max(self.cfg.task_max_minutes, self.cfg.jit_window_minutes) * 60
        k = int((t - block.start).total_seconds() // span)
        ws = block.start + timedelta(seconds=k * span)
        return ws, min(ws + timedelta(seconds=span), block.end)

    def current_task(self, identity: AgentIdentity, now: datetime) -> PlanItem | None:
        task = self.plans.at(identity.id, PlanLevel.TASK, now)
        if task is not None:
            return task
        block = self.plans.at(identity.id, PlanLevel.HOUR, now)
        if block is None:
            return None
        ws, we = self.window_of(block, now)
        start = ws
        for t in self.plans.overlapping(identity.id, PlanLevel.TASK, ws, we):
            if t.end <= now:
                start = max(start, t.end)
        start = max(start, ws)
        if start > now:  # pragma: no cover - guarded by the loop above
            start = floor_minute(now)
        return self._decompose(identity, now, block, start, we)

    def schedule_context(self, agent_id: str, d: date) -> str:
        lines = []
        for it in self.plans.items(agent_id, day=d.isoformat(), level=PlanLevel.HOUR):
            end = "24:00" if it.end.date() != it.start.date() else hhmm(it.end)
            lines.append(f"{hhmm(it.start)}–{end} {it.description}")
        return "\n".join(lines)

    def _decompose(self, identity: AgentIdentity, now: datetime, block: PlanItem, start: datetime, end: datetime) -> PlanItem | None:
        minutes = int((end - start).total_seconds() // 60)
        if minutes <= 0:
            return None
        lo, hi = self.cfg.task_min_minutes, self.cfg.task_max_minutes
        if is_sleep(block.description) or minutes <= hi:
            return self.plans.new(identity.id, PlanLevel.TASK, start, minutes, block.description, now, parent_id=block.id, day=block.day, source="block")

        def validate(out: Any) -> list[str]:
            errs = []
            if not out.tasks:
                return ["give at least one task"]
            total = 0
            for k, t in enumerate(out.tasks, start=1):
                if not t.activity.strip():
                    errs.append(f"task {k}: empty activity")
                if not (lo <= t.duration_minutes <= hi) and not (len(out.tasks) == 1 and t.duration_minutes == minutes):
                    errs.append(f"task {k}: duration {t.duration_minutes} is outside {lo}-{hi} minutes")
                total += t.duration_minutes
            if total != minutes:
                errs.append(f"durations add up to {total} minutes, need exactly {minutes}")
            return errs

        try:
            out = self.svc.gateway.run(
                "decompose",
                {
                    "agent_summary": self.summary.description(identity, now),
                    "day_label": day_label(now),
                    "first_name": identity.first_name,
                    "schedule_context": self.schedule_context(identity.id, block.start.date()),
                    "activity": block.description,
                    "start": hhmm(start),
                    "end": hhmm(end) if end.date() == start.date() else "24:00",
                    "duration": str(minutes),
                    "min_minutes": str(lo),
                    "max_minutes": str(hi),
                    "_duration": minutes,
                    "_start_min": start.hour * 60 + start.minute,
                    "_activity": block.description,
                    "_min": lo,
                    "_max": hi,
                },
                agent_id=identity.id,
                sim_time=now,
                purpose="plan:decompose",
                validate=validate,
            )
        except TaskFailed as exc:
            self.svc.events.log("plan_failure", now, identity.id, level="task", block=block.id, error=str(exc), errors=exc.errors[:5])
            return self.plans.new(
                identity.id,
                PlanLevel.TASK,
                start,
                minutes,
                block.description,
                now,
                parent_id=block.id,
                day=block.day,
                source="block",
                metadata={"decomposition_failed": True, "call_ids": exc.call_ids},
            )
        first: PlanItem | None = None
        t = start
        for task in out.output.tasks:
            item = self.plans.new(
                identity.id,
                PlanLevel.TASK,
                t,
                task.duration_minutes,
                task.activity.strip(),
                now,
                parent_id=block.id,
                day=block.day,
                source="generated",
                metadata={"call_ids": out.call_ids},
            )
            if first is None:
                first = item
            t = item.end
        cur = self.plans.at(identity.id, PlanLevel.TASK, now)
        return cur or first

    # ------------------------------------------------------------------ replanning
    def insert(
        self,
        identity: AgentIdentity,
        now: datetime,
        activity: str,
        minutes: int,
        *,
        source: str,
        location: str | None = None,
        metadata: dict[str, Any] | None = None,
        replan: bool = True,
        displace: bool = True,
    ) -> PlanItem:
        """Insert an unplanned activity at the current minute and regenerate the rest of the window.

        ``displace=False`` (waiting) pauses the plan instead: the inserted item overlays the
        current task, which resumes when the wait is over if it is still running.
        """

        minutes = max(1, int(minutes))
        start = floor_minute(now)
        end = start + timedelta(minutes=minutes)
        block = self.plans.at(identity.id, PlanLevel.HOUR, now)
        ws, we = self.window_of(block, now) if block else (start, end)
        window_end = max(we, end)
        displaced = self.plans.overlapping(identity.id, PlanLevel.TASK, start, window_end) if displace else []
        original = [(it.start, it.duration_min, it.description) for it in displaced]
        for it in displaced:
            if it.start < start:
                kept = int((start - it.start).total_seconds() // 60)
                if kept > 0:
                    it.duration_min = kept
                    self.plans.set_status(it, PlanStatus.DONE, truncated_at=iso(start))
                    continue
            self.plans.set_status(it, PlanStatus.SUPERSEDED, superseded_at=iso(now), superseded_by_source=source)
        inserted = self.plans.new(
            identity.id,
            PlanLevel.TASK,
            start,
            minutes,
            activity,
            now,
            parent_id=block.id if block else None,
            day=block.day if block else start.date().isoformat(),
            source=source,
            location=location,
            metadata=dict(metadata or {}),
        )
        self.svc.events.log(
            "replan",
            now,
            identity.id,
            inserted=activity,
            minutes=minutes,
            source=source,
            displaced=[{"start": hhmm(s), "minutes": d, "activity": a} for s, d, a in original],
        )
        if displace and replan and block is not None and end < we and not is_sleep(block.description):
            self._replan_rest(identity, now, block, inserted, we, original)
        return inserted

    def _replan_rest(
        self, identity: AgentIdentity, now: datetime, block: PlanItem, inserted: PlanItem, we: datetime, original: list[tuple[datetime, int, str]]
    ) -> None:
        rest = int((we - inserted.end).total_seconds() // 60)
        if rest <= 0:
            return
        lo, hi = self.cfg.task_min_minutes, self.cfg.task_max_minutes
        if rest <= hi:
            later = [a for s, d, a in original if s + timedelta(minutes=d) > inserted.end]
            desc = later[0] if later else block.description
            self.plans.new(identity.id, PlanLevel.TASK, inserted.end, rest, desc, now, parent_id=block.id, day=block.day, source="replan")
            return

        def validate(out: Any) -> list[str]:
            errs = []
            total = sum(t.duration_minutes for t in out.tasks)
            if total != rest:
                errs.append(f"durations add up to {total} minutes, need exactly {rest}")
            for k, t in enumerate(out.tasks, start=1):
                if not t.activity.strip():
                    errs.append(f"task {k}: empty activity")
                if not (lo <= t.duration_minutes <= hi):
                    errs.append(f"task {k}: duration {t.duration_minutes} is outside {lo}-{hi} minutes")
            return errs

        orig_lines = "\n".join(f"{hhmm(s)} ({d} min) {a}" for s, d, a in original) or f"{hhmm(block.start)} {block.description}"
        try:
            out = self.svc.gateway.run(
                "replan",
                {
                    "agent_summary": self.summary.description(identity, now),
                    "first_name": identity.first_name,
                    "window_start": hhmm(original[0][0]) if original else hhmm(inserted.start),
                    "window_end": hhmm(we) if we.date() == inserted.start.date() else "24:00",
                    "original_schedule": orig_lines,
                    "now": long_time(now),
                    "inserted_activity": inserted.description,
                    "inserted_minutes": str(inserted.duration_min),
                    "inserted_end": hhmm(inserted.end),
                    "remaining_minutes": str(rest),
                    "min_minutes": str(lo),
                    "max_minutes": str(hi),
                    "_resume_min": inserted.end.hour * 60 + inserted.end.minute,
                    "_remaining": rest,
                    "_original": [(s.hour * 60 + s.minute, d, a) for s, d, a in original],
                    "_min": lo,
                    "_max": hi,
                },
                agent_id=identity.id,
                sim_time=now,
                purpose="plan:replan",
                validate=validate,
            )
        except TaskFailed as exc:
            self.svc.events.log("plan_failure", now, identity.id, level="replan", error=str(exc), errors=exc.errors[:5])
            return  # the window is decomposed again just in time when the agent gets there
        t = inserted.end
        for task in out.output.tasks:
            item = self.plans.new(
                identity.id,
                PlanLevel.TASK,
                t,
                task.duration_minutes,
                task.activity.strip(),
                now,
                parent_id=block.id,
                day=block.day,
                source="replan",
                metadata={"call_ids": out.call_ids},
            )
            t = item.end

    # ------------------------------------------------------------------ status helpers
    def mark_active(self, item: PlanItem) -> None:
        if item.status == PlanStatus.PLANNED:
            self.plans.set_status(item, PlanStatus.ACTIVE)

    def mark_done(self, item_id: str | None, now: datetime) -> None:
        if not item_id:
            return
        item = self.plans.get(item_id)
        if item is not None and item.status in (PlanStatus.PLANNED, PlanStatus.ACTIVE) and item.end <= now:
            self.plans.set_status(item, PlanStatus.DONE)


__all__ = ["PlanStore", "Planner", "is_sleep", "floor_minute", "parse_hhmm"]
