"""Reacting to observations (paper §4.3.1 pp. 11–12; spec H-1 … H-5).

Each step, at most one newly perceived event is considered (the "focal" percept):

* other agents first (nearest), as in the released ``_choose_retrieved`` which prefers
  persona events and skips the agent's own and idle events;
* then ambient events and objects in a *lasting* non-idle state (e.g. a stove a researcher
  set to "burning"), each considered once per state while the agent is awake. The released
  code never reacts to object events (plan.py:796); the paper's examples (p. 5, a burning
  stove) need it, so this is listed as an extension (D-12).

Context follows the paper: memories are retrieved for "[observer]'s relationship with
[observed]" and "[observed] is [status]", summarized, and the agent decides whether to keep
going, react, talk or wait. "talk" is offered only when the conversation policy allows it
(neither asleep, partner free, cooldown over, not after 23:00).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..memory.retrieval import RetrievalResult
from ..providers.base import TaskFailed
from ..schemas import AgentIdentity, Memory, MemoryOrigin
from ..simulation.clock import long_time
from ..world.perception import Percept
from .context import bullet
from .services import Services
from .summary import SummaryService

NEWS_IMPORTANCE = 6
NEWS_ORIGINS = {MemoryOrigin.SEED, MemoryOrigin.INNER_VOICE, MemoryOrigin.STATEMENT}


@dataclass
class ReactionDecision:
    decision: str  # continue | react | talk | wait
    reason: str
    percept: Percept
    new_activity: str | None = None
    minutes: int | None = None
    context: str = ""
    call_ids: list[int] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)
    partner_id: str | None = None


def focal_percept(candidates: list[Percept], *, sleeping: bool) -> Percept | None:
    """Pick the one percept worth a reaction decision (or None).

    ``candidates`` are newly perceived agent events plus notable objects and ambient events
    the agent has not yet considered. Sleeping agents make no reaction decisions; what they
    perceive is still stored, and notable things are considered once they are awake.
    """

    if sleeping:
        return None
    others = [p for p in candidates if p.kind == "agent" and not p.is_idle]
    if others:
        return min(others, key=lambda p: (p.distance, p.subject))
    special = [p for p in candidates if p.kind in ("ambient", "object")]
    if special:
        return min(special, key=lambda p: (p.distance, p.subject))
    return None


def news_items(memories: list[Memory], partner_id: str | None = None) -> list[str]:
    """High-importance things the speaker knows and could bring up (read by the offline mock only).

    Only authored seeds, inner-voice statements and statements heard from someone other than
    the partner count. Real models see the same retrieved memories in the prompt and decide
    for themselves what to say.
    """

    out = []
    for m in memories:
        if m.origin not in NEWS_ORIGINS or m.importance < NEWS_IMPORTANCE:
            continue
        if m.origin == MemoryOrigin.STATEMENT and m.speaker_id == partner_id:
            continue
        if m.description not in out:
            out.append(m.description)
    return out


class ReactionEngine:
    def __init__(self, svc: Services, summary: SummaryService):
        self.svc = svc
        self.summary = summary

    def context(
        self, identity: AgentIdentity, observed: str, observed_status: str, now: datetime, *, about_agent: bool
    ) -> tuple[str, list[Memory], list[int], list[str]]:
        """Paper §4.3.1 two-query context, summarized from the observer's own memories."""

        svc = self.svc
        queries = [f"{identity.name}'s relationship with {observed}", observed_status] if about_agent else [observed_status]
        results: list[RetrievalResult] = [svc.retriever.retrieve(identity.id, q, now, purpose="reaction:context") for q in queries]
        mems: list[Memory] = []
        seen: set[str] = set()
        for r in results:
            for m in r.delivered:
                if m.id not in seen:
                    seen.add(m.id)
                    mems.append(m)
        trace_ids = [r.trace_id for r in results if r.trace_id]
        if not mems:
            return f"{identity.name} has no memories about {observed}.", mems, [], trace_ids
        out = svc.gateway.run(
            "interaction_context",
            {
                "observer": identity.name,
                "observed": observed,
                "statements": bullet(mems),
                "observed_status": f"(currently: {observed_status})",
                "_observer": identity.name,
                "_observed": observed,
                "_statements": [m.description for m in mems],
                "_observed_status": observed_status.split(" is ", 1)[-1] if " is " in observed_status else observed_status,
            },
            agent_id=identity.id,
            sim_time=now,
            purpose="reaction:context",
        )
        return out.output.summary.strip(), mems, out.call_ids, trace_ids

    def decide(
        self,
        identity: AgentIdentity,
        percept: Percept,
        now: datetime,
        *,
        status: str,
        can_talk: bool,
        observed_name: str | None = None,
    ) -> ReactionDecision:
        about_agent = percept.kind == "agent"
        observed = observed_name or percept.subject.rsplit(":", 1)[-1]
        try:
            ctx, mems, ctx_calls, traces = self.context(identity, observed, percept.description, now, about_agent=about_agent)
        except TaskFailed as exc:
            return ReactionDecision("continue", f"context failed: {exc}", percept, call_ids=exc.call_ids)
        first = observed.split()[0] if observed else ""
        knows = about_agent and any(first and first in m.description for m in mems)
        talk_option = f'- "talk": start a conversation with {observed}.' if (about_agent and can_talk) else ""
        allowed = {"continue", "react", "wait"} | ({"talk"} if about_agent and can_talk else set())

        def validate(out: Any) -> list[str]:
            errs = []
            if out.decision not in allowed:
                errs.append(f"decision must be one of {sorted(allowed)}")
            if out.decision == "react":
                if not (out.new_activity or "").strip():
                    errs.append("a reaction needs new_activity")
                if not out.duration_minutes or not (1 <= out.duration_minutes <= 240):
                    errs.append("a reaction needs duration_minutes between 1 and 240")
            if out.decision == "wait" and (not out.duration_minutes or not (1 <= out.duration_minutes <= 120)):
                errs.append("waiting needs duration_minutes between 1 and 120")
            return errs

        try:
            out = self.svc.gateway.run(
                "reaction",
                {
                    "agent_summary": self.summary.description(identity, now),
                    "now": long_time(now),
                    "agent_name": identity.name,
                    "status": status,
                    "observation": percept.description,
                    "context": ctx,
                    "talk_option": talk_option,
                    "_observation": percept.description,
                    "_observed_is_agent": about_agent,
                    "_percept_kind": percept.kind,
                    "_can_talk": about_agent and can_talk,
                    "_knows_observed": knows,
                    "_has_news": bool(news_items(mems, percept.agent_id)),
                },
                agent_id=identity.id,
                sim_time=now,
                purpose="reaction:decide",
                validate=validate,
            )
        except TaskFailed as exc:
            return ReactionDecision("continue", f"decision failed: {exc}", percept, context=ctx, call_ids=ctx_calls + exc.call_ids, trace_ids=traces)
        o = out.output
        return ReactionDecision(
            o.decision,
            o.reason,
            percept,
            new_activity=(o.new_activity or "").strip() or None,
            minutes=o.duration_minutes,
            context=ctx,
            call_ids=ctx_calls + out.call_ids,
            trace_ids=traces,
            partner_id=percept.agent_id if o.decision == "talk" else None,
        )
