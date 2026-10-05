"""Turn-by-turn dialogue (paper §4.3.1 p. 12; spec I-1 … I-8).

Each utterance is generated separately, conditioned on the speaker's own memories: a summary
of the speaker's relationship with the partner (retrieved once per conversation, as the
paper's first utterance is) and memories retrieved for the partner's last utterance, plus the
dialogue so far. A turn may end the conversation; there is a hard cap on utterances.

What is stored: every utterance in both participants' streams (the speaker's as
``own_statement``, the listener's as ``statement``, "Name said to Name: \"...\"") and a
one-sentence conversation summary for both. Utterances never reach agents who were not in
the conversation; bystanders only perceive "A is chatting with B". Both participants' plans
are revised from the end of the conversation (§4.3.1). The released code's
post-conversation planning note and memo are added only when
``architecture.post_conversation_inferences`` is on (released-code fidelity).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ..providers.base import TaskFailed
from ..schemas import AgentIdentity, Conversation, Memory, MemoryKind, MemoryOrigin, Utterance
from ..simulation.clock import long_time
from .context import bullet
from .reaction import ReactionEngine, news_items
from .services import Services
from .summary import SummaryService


@dataclass
class Side:
    identity: AgentIdentity
    status: str
    sees: str  # what this participant observes of the partner
    relationship: str = ""
    relationship_memories: list[Memory] = field(default_factory=list)


def conversation_minutes(utterances: list[Utterance]) -> int:
    """Released duration rule: ceil((characters / 8) / 30) minutes (plan.py ``_chat_react``)."""

    chars = sum(len(u.text) for u in utterances)
    return max(1, math.ceil(int(chars / 8) / 30))


def transcript_text(conv: Conversation, names: dict[str, str]) -> str:
    return "\n".join(f"{names[u.speaker_id]}: {u.text}" for u in conv.utterances)


class DialogueEngine:
    def __init__(self, svc: Services, summary: SummaryService, reaction: ReactionEngine):
        self.svc = svc
        self.summary = summary
        self.reaction = reaction
        self.cfg = svc.cfg.dialogue

    def next_id(self) -> str:
        row = self.svc.db.one("SELECT COUNT(*) AS n FROM conversations")
        return f"c{(int(row['n']) if row else 0) + 1:05d}"

    def run(self, a: Side, b: Side, now: datetime, location: str | None, trigger: str = "") -> Conversation:
        svc = self.svc
        conv = Conversation(id=self.next_id(), participants=[a.identity.id, b.identity.id], initiator_id=a.identity.id, started_at=now, location=location)
        conv.metadata["trigger"] = trigger
        names = {a.identity.id: a.identity.name, b.identity.id: b.identity.name}
        call_ids: list[int] = []
        traces: list[str] = []
        try:
            for me, other in ((a, b), (b, a)):
                text, mems, ids, tr = self.reaction.context(me.identity, other.identity.name, me.sees, now, about_agent=True)
                me.relationship, me.relationship_memories = text, mems
                call_ids += ids
                traces += tr
            sides = (a, b)
            for i in range(self.cfg.max_utterances):
                me, other = sides[i % 2], sides[(i + 1) % 2]
                last = conv.utterances[-1].text if conv.utterances else ""
                query = last or f"{me.identity.name}'s relationship with {other.identity.name}"
                res = svc.retriever.retrieve(me.identity.id, query, now, max_items=self.cfg.turn_items, purpose="dialogue:turn")
                if res.trace_id:
                    traces.append(res.trace_id)
                turn_mems = [m for m in res.delivered if m.id not in {x.id for x in me.relationship_memories}]
                transcript = transcript_text(conv, names) or "(the conversation has not started yet)"
                intent = f"{me.identity.name} is starting a conversation with {other.identity.name}." if i == 0 else ""
                out = svc.gateway.run(
                    "dialogue_turn",
                    {
                        "agent_summary": self.summary.description(me.identity, now),
                        "now": long_time(now),
                        "agent_name": me.identity.name,
                        "status": me.status,
                        "observation": me.sees,
                        "location": location or "outside",
                        "relationship_summary": me.relationship,
                        "turn_memories": bullet(turn_mems) if turn_mems else "",
                        "intent": intent,
                        "transcript": transcript,
                        "partner_name": other.identity.name,
                        "_speaker": me.identity.name,
                        "_partner": other.identity.name,
                        "_turn_index": i,
                        "_news": news_items(me.relationship_memories + res.delivered, other.identity.id),
                        "_transcript_text": transcript_text(conv, names),
                        "_conversation_id": conv.id,
                        "_last_utterance": last,
                    },
                    agent_id=me.identity.id,
                    sim_time=now,
                    purpose="dialogue:turn",
                )
                call_ids += out.call_ids
                conv.utterances.append(
                    Utterance(speaker_id=me.identity.id, text=out.output.utterance.strip(), sim_time=now, end_conversation=bool(out.output.end_conversation))
                )
                if out.output.end_conversation and i >= 1:
                    conv.reason = "ended by speaker"
                    break
            else:
                conv.reason = f"reached the {self.cfg.max_utterances}-utterance limit"
            conv.status = "completed"
        except TaskFailed as exc:
            conv.status = "failed"
            conv.reason = f"aborted: {exc}"
            call_ids += exc.call_ids
        minutes = conversation_minutes(conv.utterances) if conv.utterances else 1
        conv.ended_at = now + timedelta(minutes=minutes)
        conv.metadata.update({"call_ids": call_ids, "trace_ids": traces, "minutes": minutes})
        if conv.utterances:
            self._store(conv, a.identity, b.identity, now, names)
        self.save(conv)
        svc.events.log(
            "conversation",
            now,
            a.identity.id,
            conversation_id=conv.id,
            participants=conv.participants,
            status=conv.status,
            utterances=len(conv.utterances),
            minutes=minutes,
            location=location,
            summary=conv.summary,
            reason=conv.reason,
        )
        return conv

    def _store(self, conv: Conversation, a: AgentIdentity, b: AgentIdentity, now: datetime, names: dict[str, str]) -> None:
        svc = self.svc
        text = transcript_text(conv, names)
        try:
            out = svc.gateway.run(
                "conversation_summary",
                {"transcript": text, "_transcript_text": text},
                agent_id=a.id,
                sim_time=now,
                purpose="dialogue:summary",
            )
            conv.summary = out.output.summary.strip()
        except TaskFailed:
            conv.summary = None
        for me, other in ((a, b), (b, a)):
            lines: list[tuple[str, MemoryOrigin, Utterance]] = []
            for u in conv.utterances:
                speaker = names[u.speaker_id]
                listener = other.name if u.speaker_id == me.id else me.name
                origin = MemoryOrigin.OWN_STATEMENT if u.speaker_id == me.id else MemoryOrigin.STATEMENT
                lines.append((f'{speaker} said to {listener}: "{u.text}"', origin, u))
            texts = [t for t, _, _ in lines]
            if conv.summary:
                texts.append(f"{me.name} had a conversation with {other.name}. {conv.summary}")
            try:
                scores = svc.importance.score_batch(me, texts, now, purpose="importance:conversation", kind="conversation")
            except TaskFailed:
                scores = [None] * len(texts)  # fall back to one call per memory inside remember()
            for (t, origin, u), score in zip(lines, scores, strict=False):
                svc.remember(
                    me,
                    t,
                    MemoryKind.OBSERVATION,
                    origin,
                    now,
                    importance=score,
                    importance_kind="conversation",
                    conversation_id=conv.id,
                    speaker_id=u.speaker_id,
                    location=conv.location,
                )
            if conv.summary:
                svc.remember(
                    me,
                    texts[-1],
                    MemoryKind.OBSERVATION,
                    MemoryOrigin.CONVERSATION,
                    now,
                    importance=scores[-1],
                    importance_kind="conversation",
                    conversation_id=conv.id,
                    location=conv.location,
                )
            if svc.cfg.architecture.conversation_inferences_enabled():
                self._inferences(me, conv, text, now)

    def _inferences(self, me: AgentIdentity, conv: Conversation, text: str, now: datetime) -> None:
        """Released-code planning thought and memo after a conversation (plan.py, converse.py)."""

        try:
            out = self.svc.gateway.run(
                "conversation_inferences",
                {"transcript": text, "agent_name": me.name, "_transcript_text": text, "_name": me.name},
                agent_id=me.id,
                sim_time=now,
                purpose="dialogue:inferences",
            )
        except TaskFailed:
            return
        if out.output.planning_note:
            self.svc.remember(
                me,
                f"For {me.name}'s planning: {out.output.planning_note}",
                MemoryKind.PLAN,
                MemoryOrigin.INFERENCE,
                now,
                importance_kind="thought",
                conversation_id=conv.id,
            )
        if out.output.memo:
            self.svc.remember(me, out.output.memo, MemoryKind.REFLECTION, MemoryOrigin.INFERENCE, now, importance_kind="thought", conversation_id=conv.id)

    def save(self, conv: Conversation) -> None:
        self.svc.db.execute(
            """INSERT INTO conversations(id, started_at, status, participants, json) VALUES(?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET status=excluded.status, json=excluded.json""",
            (conv.id, conv.started_at.isoformat(), conv.status, ",".join(conv.participants), conv.model_dump_json()),
        )

    def get(self, conv_id: str) -> Conversation | None:
        row = self.svc.db.one("SELECT json FROM conversations WHERE id=?", (conv_id,))
        return Conversation.model_validate_json(row["json"]) if row else None

    @staticmethod
    def as_dict(conv: Conversation) -> dict[str, Any]:
        return conv.model_dump(mode="json")
