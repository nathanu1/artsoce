"""The town game layer: player actions on top of the paper's simulation (an extension).

What the player does reaches residents only through the world, the way a visitor would:

* talking, giving a gift or delivering a request is an exchange with "the town builder";
  the resident's reply is generated from the resident's own memories (``player_chat``) and
  both lines are stored in the resident's memory stream, like any conversation;
* a request is generated from the resident's own identity, plan, memories and known places
  (``resident_request``) and the resident remembers having asked;
* placed items become world objects that residents perceive, learn and may use;
* the paper's two user interventions are kept: editing an object's state and the inner voice.

Game meters (friendship, Town Pulse, motifs, affinity scores) are bookkeeping for the player.
They are never put into a prompt. Model calls go through the same gateway and ledger as the
simulation, at the step the action is applied, so a played run resumes and replays exactly.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..cognition.context import bullet
from ..db import iso
from ..providers.base import TaskFailed
from ..schemas import MemoryKind, MemoryOrigin, PlanLevel
from ..simulation.clock import long_time
from .actions import Action, ActionLog
from .affinity import Affinity
from .content import GameContent, load_content
from .store import GameStore
from .world_edit import Draft, PlacedItem, WorldEditor, apply_zones

_POSSESSIVE = re.compile(r"([A-Za-z][A-Za-z .'-]*?)'s\b")


class GameRuleError(Exception):
    """The action is not possible right now (a sleeping resident, too few motifs, ...)."""


def _stable_index(n: int, *parts: Any) -> int:
    h = hashlib.sha256("␟".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:4], "little") % max(1, n)


class GameLayer:
    def __init__(self, sim: Any, *, actions_path: str | Path, readonly_actions: bool = False, content: GameContent | None = None):
        self.sim = sim
        self.cfg = sim.cfg.game
        self.content = content or load_content(self.cfg.content_dir)
        self.content_sha256 = hashlib.sha256(self.content.model_dump_json().encode()).hexdigest()
        self.aff = Affinity(self.content)
        self.store = GameStore(sim.db)
        self.actions = ActionLog(actions_path, readonly=readonly_actions)
        self.zones = apply_zones(sim.world, self.content.zones)
        self.editor = WorldEditor(sim.world, sim.nav, sim.perceiver, self.content)
        self.builder = self.cfg.builder_name
        self.builder_cap = self.builder[:1].upper() + self.builder[1:]
        self.residents = {aid: self.aff.resident(ident) for aid, ident in sim.identities.items()}
        self.listeners: list[Callable[[dict[str, Any]], None]] = []
        recorded = sim.db.get_meta("game_content_sha256")
        if recorded and recorded != self.content_sha256:
            raise RuntimeError("the game content (configs/game) changed since this run started; start a new run instead of resuming")
        if not recorded:
            sim.db.set_meta("game_content_sha256", self.content_sha256)
        self.editor.apply(self.store.items())
        sim.before_step_hooks.append(self.before_step)
        sim.after_step_hooks.append(self.after_step)
        sim.flush_hooks.append(self.store.flush)
        sim.invalidate_hooks.append(self.invalidate)

    # ================================================================== engine hooks
    def before_step(self, now: datetime) -> None:
        self.ensure_started(now)
        self.apply_due(now)
        if self.cfg.auto_requests:
            self._auto_request(now)

    def ensure_started(self, now: datetime) -> None:
        """Hand out the starting motifs once, before the first action of the run."""

        if not self.store.kv.get("granted_start"):
            self._grant_start(now)

    def apply_due(self, now: datetime) -> int:
        """Apply logged player actions due at the current step (also used while paused)."""

        n = 0
        for act in self.actions.due(self.sim.clock.step, int(self.store.get("applied_seq"))):
            self._apply(act, now)
            self.store.put("applied_seq", act.seq)
            n += 1
        return n

    def after_step(self, now: datetime) -> None:
        self._sparkles_from_conversations(now)

    def invalidate(self) -> None:
        self.store.load()
        self.editor.apply(self.store.items())

    def manifest(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "content_dir": self.cfg.content_dir,
            "content_sha256": self.content_sha256,
            "actions": len(self.actions),
            "builder_name": self.builder,
            "note": "game layer (extension): player actions are logged in actions.jsonl and applied at step boundaries",
        }

    # ================================================================== events and meters
    def _event(self, now: datetime, kind: str, agent: str | None = None, action: Action | None = None, **payload: Any) -> dict[str, Any]:
        step = self.sim.clock.step
        eid = self.store.log(step, iso(now) or "", kind, agent, payload, action.seq if action else None)
        ev = {"id": eid, "step": step, "sim_time": iso(now), "kind": kind, "agent_id": agent, "action_seq": action.seq if action else None, **payload}
        for fn in self.listeners:
            fn(ev)
        return ev

    def _award(self, now: datetime, reason: str, points: int | None = None) -> int:
        pts = self.content.points.get(reason, 0) if points is None else points
        if pts <= 0:
            return 0
        pulse = self.store.get("pulse")
        before = self.content.level_for(int(pulse["points"])).level
        pulse["points"] = int(pulse["points"]) + pts
        after = self.content.level_for(pulse["points"])
        pulse["level"] = after.level
        self.store.touch("pulse")
        if after.level > before:
            self._event(
                now,
                "level_up",
                level=after.level,
                name=after.name,
                unlocked_items=[i.id for i in self.content.items if before < i.unlock <= after.level],
                unlocked_templates=[t.id for t in self.content.templates if before < t.unlock <= after.level],
            )
        return pts

    def level(self) -> int:
        return int(self.store.get("pulse")["level"])

    def _befriend(self, agent: str, reason: str) -> int:
        amount = self.content.friendship.get(reason, 0)
        fr = self.store.get("friendship")
        fr[agent] = max(0, min(100, int(fr.get(agent, 0)) + amount))
        self.store.touch("friendship")
        return amount

    def _gain_motif(self, now: datetime, motif_id: str, n: int = 1) -> None:
        inv = self.store.get("inventory")
        inv[motif_id] = int(inv.get(motif_id, 0)) + n
        found = self.store.get("found")
        found.setdefault(motif_id, iso(now))
        self.store.touch("inventory")
        self.store.touch("found")
        self.store.get("stats")["motifs_found"] += n
        self.store.touch("stats")

    def theme_counts(self) -> dict[str, int]:
        out = {t.id: 0 for t in self.content.themes}
        for m in self.content.motifs:
            out[m.theme] += int(self.store.get("inventory").get(m.id, 0))
        return out

    def _spend(self, cost: dict[str, int]) -> dict[str, int]:
        """Take ``cost`` (theme -> count) from the inventory, most plentiful motifs first."""

        have = self.theme_counts()
        short = [f"{n - have[t]} more {self.content.theme(t).name}" for t, n in cost.items() if n > have[t]]
        if short:
            raise GameRuleError("needs " + " and ".join(short) + " motifs")
        inv = self.store.get("inventory")
        spent: dict[str, int] = {}
        for t, n in cost.items():
            for _ in range(n):
                pool = sorted((m for m in self.content.motifs if m.theme == t and inv.get(m.id, 0) > 0), key=lambda m: (-inv[m.id], m.id))
                inv[pool[0].id] -= 1
                spent[pool[0].id] = spent.get(pool[0].id, 0) + 1
        self.store.touch("inventory")
        return spent

    def _refund(self, cost: dict[str, int]) -> None:
        for t, n in cost.items():
            motif = self.content.motifs_for(t, "environment")[0]
            inv = self.store.get("inventory")
            inv[motif.id] = int(inv.get(motif.id, 0)) + n
        self.store.touch("inventory")

    def _grant_start(self, now: datetime) -> None:
        granted = {}
        for t in self.content.themes:
            motif = self.content.motifs_for(t.id, "environment")[0]
            if self.cfg.starting_motifs > 0:
                self._gain_motif(now, motif.id, self.cfg.starting_motifs)
                granted[motif.id] = self.cfg.starting_motifs
        self.store.put("granted_start", True)
        self._event(now, "welcome", granted=granted)

    # ================================================================== actions
    def _apply(self, act: Action, now: datetime) -> None:
        handler = getattr(self, f"_do_{act.kind}", None)
        try:
            if handler is None:
                raise GameRuleError(f"unknown action {act.kind}")
            handler(act, now)
        except GameRuleError as exc:
            self._event(now, "rejected", act.payload.get("agent"), act, action_kind=act.kind, reason=str(exc), payload=act.payload)
        except TaskFailed as exc:
            # The model could not produce a valid answer after a repair: nothing is invented.
            self._event(now, "failed", act.payload.get("agent"), act, action_kind=act.kind, reason=str(exc), call_ids=exc.call_ids)

    # ---------------------------------------------------------------- residents
    def _resident(self, agent: str) -> Any:
        ident = self.sim.identities.get(agent)
        if ident is None:
            raise GameRuleError(f"no resident {agent}")
        return ident

    def _available(self, ident: Any) -> Any:
        view = self.sim.view_of(ident.id)
        if view.sleeping:
            raise GameRuleError(f"{ident.first_name} is asleep")
        if view.conversation_partner:
            raise GameRuleError(f"{ident.first_name} is talking with {view.conversation_partner}")
        return view

    def _history(self, agent: str) -> str:
        lines: list[str] = []
        for ev in self.store.events(kinds=("chat", "gift", "delivered", "request")):
            if ev["agent_id"] != agent:
                continue
            if ev.get("builder_line"):
                lines.append(f"{self.builder_cap}: {ev['builder_line']}")
            if ev.get("reply"):
                lines.append(f"{self.sim.identities[agent].name}: {ev['reply']}")
        return "\n".join(lines[-self.cfg.chat_history_lines :])

    def _reply(self, ident: Any, view: Any, now: datetime, utterance: str, *, event_note: str = "", mock: dict[str, Any] | None = None) -> Any:
        svc = self.sim.svc
        res = svc.retriever.retrieve(ident.id, utterance, now, max_items=self.cfg.chat_memories, purpose="game:chat")
        about = svc.retriever.retrieve(ident.id, f"{ident.name} and {self.builder}", now, max_items=3, purpose="game:chat:builder")
        mems, seen = [], set()
        for m in res.delivered + about.delivered:
            if m.id not in seen:
                seen.add(m.id)
                mems.append(m)
        status = view.activity or "idle"
        location = view.address.split(":", 1)[1] if view.address and ":" in view.address else (view.address or "outside")
        out = svc.gateway.run(
            "player_chat",
            {
                "agent_summary": self.sim.summary.description(ident, now),
                "now": long_time(now),
                "agent_name": ident.name,
                "status": status,
                "location": location,
                "memories": bullet(mems),
                "history": self._history(ident.id) or "(nothing yet today)",
                "event": event_note,
                "builder": self.builder,
                "builder_cap": self.builder_cap,
                "utterance": utterance,
                "_first_name": ident.first_name,
                "_utterance": utterance,
                "_status": status,
                "_memory_texts": [m.description for m in mems],
                **(mock or {}),
            },
            agent_id=ident.id,
            sim_time=now,
            purpose="game:chat",
        )
        return out.output

    def _remember_exchange(self, ident: Any, view: Any, now: datetime, builder_line: str, reply: str) -> None:
        svc = self.sim.svc
        lines = [
            (f'{self.builder_cap} said to {ident.name}: "{builder_line}"', MemoryOrigin.STATEMENT, "builder"),
            (f'{ident.name} said to {self.builder}: "{reply}"', MemoryOrigin.OWN_STATEMENT, ident.id),
        ]
        texts = [t for t, _, _ in lines]
        try:
            scores = svc.importance.score_batch(ident, texts, now, purpose="importance:game", kind="conversation")
        except TaskFailed:
            scores = [None] * len(texts)
        for (text, origin, speaker), score in zip(lines, scores, strict=False):
            svc.remember(
                ident,
                text,
                MemoryKind.OBSERVATION,
                origin,
                now,
                importance=score,
                importance_kind="conversation",
                speaker_id=speaker,
                location=view.address,
                metadata={"game": "builder_exchange"},
            )

    def _do_chat(self, act: Action, now: datetime) -> None:
        ident = self._resident(act.payload.get("agent", ""))
        text = " ".join(str(act.payload.get("text", "")).split())[:400]
        if not text:
            raise GameRuleError("say something first")
        view = self._available(ident)
        reply = self._reply(ident, view, now, text)
        self._remember_exchange(ident, view, now, text, reply.utterance)
        gained = friendship = 0
        hours = self.store.get("chat_hours")
        key = now.strftime("%Y-%m-%dT%H")
        if hours.get(ident.id) != key:
            hours[ident.id] = key
            self.store.touch("chat_hours")
            gained = self._award(now, "chat")
            friendship = self._befriend(ident.id, "chat")
        self.store.get("stats")["chats"] += 1
        self.store.touch("stats")
        self._event(now, "chat", ident.id, act, builder_line=text, reply=reply.utterance, mood=reply.mood, pulse=gained, friendship=friendship)

    def _do_gift(self, act: Action, now: datetime) -> None:
        ident = self._resident(act.payload.get("agent", ""))
        try:
            gift = self.content.gift(str(act.payload.get("gift")))
        except KeyError as exc:
            raise GameRuleError(str(exc)) from exc
        view = self._available(ident)
        spent = self._spend({gift.theme: gift.cost})
        loved = self.aff.reaction(self.residents[ident.id]["loves"], gift.theme) == "loved"
        line = f"I made you a {gift.name}. I hope you like it!"
        reply = self._reply(
            ident, view, now, line, event_note=f"{self.builder_cap} hands {ident.name} a {gift.name}.", mock={"_gift": gift.name, "_gift_loved": loved}
        )
        self._remember_exchange(ident, view, now, line, reply.utterance)
        gained = self._award(now, "gift") + (self._award(now, "gift_loved") if loved else 0)
        friendship = self._befriend(ident.id, "gift_loved" if loved else "gift")
        self.store.get("stats")["gifts"] += 1
        self.store.touch("stats")
        self._event(
            now,
            "gift",
            ident.id,
            act,
            gift=gift.id,
            loved=loved,
            builder_line=line,
            reply=reply.utterance,
            mood=reply.mood,
            spent=spent,
            pulse=gained,
            friendship=friendship,
        )

    # ---------------------------------------------------------------- requests
    def _open_request(self, agent: str) -> dict[str, Any] | None:
        for r in self.store.requests(agent_id=agent):
            if r["status"] in ("open", "ready"):
                return r
        return None

    def _request_places(self, ident: Any) -> list[dict[str, Any]]:
        spatial = self.sim.spatial.get(ident.id)
        world = self.sim.world
        level = self.level()
        names = {ident.first_name.lower(), ident.last_name.lower()}
        out = []
        for w in spatial.worlds():
            for sector in spatial.sectors(w):
                for arena in spatial.arenas(w, sector):
                    address = f"{w}:{sector}:{arena}"
                    if not world.exists(address) or "bathroom" in arena.lower():
                        continue
                    owners = [m.group(1).lower() for m in _POSSESSIVE.finditer(f"{sector} {arena}")]
                    if owners and not any(n in o.split() for o in owners for n in names):
                        continue  # somebody else's home or room
                    outdoor = self.editor.is_outdoor(address)
                    fits = sorted(
                        {it.theme for it in self.content.items if it.unlock <= level and (it.placement == "any" or (it.placement == "outdoor") == outdoor)}
                    )
                    out.append({"label": f"{sector}: {arena}", "address": address, "outdoor": outdoor, "fits": fits})
        return sorted(out, key=lambda p: p["label"])[:14]

    def _generate_request(self, ident: Any, now: datetime, trigger: str, act: Action | None = None) -> dict[str, Any]:
        places = self._request_places(ident)
        if not places:
            raise GameRuleError(f"{ident.first_name} does not know a place to put anything yet")
        svc = self.sim.svc
        today = now.date().isoformat()
        blocks = self.sim.plans.items(ident.id, day=today, level=PlanLevel.HOUR)
        plan = "\n".join(f"- {b.start:%H:%M} {b.description}" for b in blocks) or "(no plan yet)"
        mems = svc.retriever.retrieve(
            ident.id, f"What would make {ident.name}'s days better? {ident.name}'s goals and needs.", now, max_items=8, purpose="game:request"
        )
        theme_ids = [t.id for t in self.content.themes]
        labels = {p["label"]: p for p in places}

        def validate(out: Any) -> list[str]:
            errors = []
            if out.theme not in theme_ids:
                errors.append(f"theme must be one of {', '.join(theme_ids)}")
            elif out.place not in labels:
                errors.append("place must be copied exactly from the list of places")
            elif out.theme not in labels[out.place]["fits"]:
                errors.append(f"nothing of the kind {out.theme} fits at {out.place}; choose another place or kind")
            return errors

        out = svc.gateway.run(
            "resident_request",
            {
                "agent_summary": self.sim.summary.description(ident, now),
                "now": long_time(now),
                "agent_name": ident.name,
                "plan": plan,
                "memories": bullet(mems.delivered),
                "builder": self.builder,
                "builder_cap": self.builder_cap,
                "themes": "\n".join(f"- {t.id} ({t.name}): {t.description}" for t in self.content.themes),
                "places": "\n".join(f"- {p['label']}" for p in places),
                "_theme_ids": theme_ids,
                "_identity_themes": list(self.residents[ident.id]["loves"]),  # mock fixture hint only; not in the prompt
                "_place_options": places,
            },
            agent_id=ident.id,
            sim_time=now,
            purpose="game:request",
            validate=validate,
        )
        o = out.output
        place = labels[o.place]
        req = {
            "id": self.store.next_id("request", "r"),
            "agent_id": ident.id,
            "wish": o.wish,
            "theme": o.theme,
            "place_label": o.place,
            "place_address": place["address"],
            "outdoor": place["outdoor"],
            "reason": o.reason,
            "request_line": o.request_line,
            "status": "open",
            "item_id": None,
            "created_at": iso(now),
            "step": self.sim.clock.step,
            "trigger": trigger,
            "call_ids": out.call_ids,
        }
        self.store.save_request(req)
        svc.remember(
            ident,
            f'{ident.name} said to {self.builder}: "{o.request_line}"',
            MemoryKind.OBSERVATION,
            MemoryOrigin.OWN_STATEMENT,
            now,
            importance_kind="conversation",
            speaker_id=ident.id,
            metadata={"game": "request", "request": req["id"]},
        )
        self._event(now, "request", ident.id, act, request=req, reply=o.request_line)
        self._refresh_requests(now)
        return req

    def _do_ask_request(self, act: Action, now: datetime) -> None:
        ident = self._resident(act.payload.get("agent", ""))
        self._available(ident)
        existing = self._open_request(ident.id)
        if existing:
            raise GameRuleError(f"{ident.first_name} already asked for {existing['wish']}")
        self._generate_request(ident, now, "asked", act)

    def _auto_request(self, now: datetime) -> None:
        if now.hour < self.cfg.request_hour:
            return
        today = now.date().isoformat()
        done = self.store.get("requests_day")
        for aid in self.sim.order:
            if done.get(aid) == today or self._open_request(aid):
                continue
            view = self.sim.view_of(aid)
            if view.sleeping or view.conversation_partner:
                continue
            done[aid] = today
            self.store.touch("requests_day")
            try:
                self._generate_request(self.sim.identities[aid], now, "auto")
            except (GameRuleError, TaskFailed) as exc:
                self._event(now, "request_failed", aid, reason=str(exc))
            return  # at most one new request per step

    def _refresh_requests(self, now: datetime) -> None:
        items = self.store.items()
        for req in self.store.requests():
            if req["status"] not in ("open", "ready"):
                continue
            match = next(
                (p for p in items if self.content.item(p.catalog_id).theme == req["theme"] and p.address.rsplit(":", 1)[0] == req["place_address"]),
                None,
            )
            status = "ready" if match else "open"
            item_id = match.id if match else None
            if (status, item_id) != (req["status"], req.get("item_id")):
                req["status"], req["item_id"] = status, item_id
                self.store.save_request(req)
                if status == "ready":
                    self._event(now, "request_ready", req["agent_id"], request=req)

    def _do_deliver(self, act: Action, now: datetime) -> None:
        req = next((r for r in self.store.requests() if r["id"] == act.payload.get("request")), None)
        if req is None:
            raise GameRuleError("no such request")
        if req["status"] != "ready":
            raise GameRuleError("place something that fits the request first")
        ident = self._resident(req["agent_id"])
        view = self._available(ident)
        item = next((p for p in self.store.items() if p.id == req["item_id"]), None)
        if item is None:
            raise GameRuleError("the item for this request is gone")
        place = req["place_label"].split(": ", 1)[-1]
        wish = re.sub(r"^(a|an|the|some)\s+", "", req["wish"].strip(), flags=re.IGNORECASE)
        line = f"I made the {wish} you asked for. There is a new {item.name} in the {place} now!"
        reply = self._reply(ident, view, now, line, event_note=f"{self.builder_cap} shows {ident.name} the new {item.name}.", mock={"_delivery": req["wish"]})
        self._remember_exchange(ident, view, now, line, reply.utterance)
        req["status"] = "fulfilled"
        req["fulfilled_at"] = iso(now)
        self.store.save_request(req)
        social = self.content.motifs_for(req["theme"], "social")[0]
        self._gain_motif(now, social.id)
        gained = self._award(now, "request_fulfilled")
        friendship = self._befriend(ident.id, "request_fulfilled")
        self.store.get("stats")["requests_fulfilled"] += 1
        self.store.touch("stats")
        self._event(
            now,
            "delivered",
            ident.id,
            act,
            request=req,
            builder_line=line,
            reply=reply.utterance,
            mood=reply.mood,
            reward=social.id,
            pulse=gained,
            friendship=friendship,
        )

    # ---------------------------------------------------------------- motifs
    def _do_search(self, act: Action, now: datetime) -> None:
        address = str(act.payload.get("address", ""))
        if address.count(":") != 3 or not self.sim.world.exists(address):
            raise GameRuleError("there is nothing to search there")
        if any(p.address == address for p in self.store.items()):
            raise GameRuleError("things you placed have nothing hidden in them")
        cool = self.store.get("cooldowns")
        until = cool.get(address)
        if until and datetime.fromisoformat(until) > now:
            raise GameRuleError(f"already searched; try again after {datetime.fromisoformat(until):%H:%M}")
        cool[address] = iso(now + timedelta(minutes=self.cfg.search_cooldown_minutes))
        self.store.touch("cooldowns")
        theme = self.aff.search_theme(address)
        name = address.rsplit(":", 1)[-1]
        if theme is None:
            self._event(now, "search_empty", None, act, address=address, object=name)
            return
        pool = self.content.motifs_for(theme, "environment")
        motif = pool[_stable_index(len(pool), self.sim.cfg.run.seed, address, now.strftime("%Y-%m-%dT%H"))]
        self._gain_motif(now, motif.id)
        gained = self._award(now, "motif_found")
        self._event(now, "motif", None, act, motif=motif.id, theme=theme, source="search", address=address, object=name, pulse=gained)

    def _sparkles_from_conversations(self, now: datetime) -> None:
        cursor = int(self.store.kv.get("conversation_cursor", 0))
        rows = self.sim.db.query("SELECT id, json FROM conversations ORDER BY id")
        sparkles = self.store.get("sparkles")
        changed = False
        for row in rows:
            num = int(row["id"].lstrip("c") or 0)
            if num <= cursor:
                continue
            conv = json.loads(row["json"])
            cursor = max(cursor, num)
            if conv.get("status") != "completed" or not conv.get("utterances"):
                continue
            text = " ".join([conv.get("summary") or ""] + [u.get("text", "") for u in conv["utterances"]])
            theme = self.aff.classify(text) or self.content.themes[-1].id
            motif = self.content.motifs_for(theme, "social")[0]
            initiator = conv.get("initiator_id") or conv["participants"][0]
            tile = self.sim.svc.states.get(initiator).tile
            ended = conv.get("ended_at") or iso(now)
            sparkles.append(
                {
                    "id": f"s{row['id']}",
                    "conversation_id": row["id"],
                    "participants": conv["participants"],
                    "tile": list(tile) if tile else None,
                    "theme": theme,
                    "motif": motif.id,
                    "appears_at": ended,
                    "expires_at": iso(datetime.fromisoformat(ended) + timedelta(minutes=self.cfg.sparkle_minutes)),
                    "collected": False,
                }
            )
            changed = True
            self.store.get("stats")["conversations"] += 1
            self.store.touch("stats")
            gained = self._award(now, "resident_conversation")
            self._event(now, "sparkle", initiator, conversation_id=row["id"], participants=conv["participants"], theme=theme, motif=motif.id, pulse=gained)
        if cursor != int(self.store.kv.get("conversation_cursor", 0)):
            self.store.put("conversation_cursor", cursor)
        keep = [s for s in sparkles if not s["collected"] and datetime.fromisoformat(s["expires_at"]) > now - timedelta(hours=1)]
        if changed or len(keep) != len(sparkles):
            self.store.put("sparkles", keep)

    def visible_sparkles(self, now: datetime) -> list[dict[str, Any]]:
        return [
            s
            for s in self.store.get("sparkles")
            if not s["collected"] and s.get("tile") and datetime.fromisoformat(s["appears_at"]) <= now < datetime.fromisoformat(s["expires_at"])
        ]

    def _do_collect_sparkle(self, act: Action, now: datetime) -> None:
        sid = act.payload.get("sparkle")
        sp = next((s for s in self.visible_sparkles(now) if s["id"] == sid), None)
        if sp is None:
            raise GameRuleError("that sparkle is gone")
        sp["collected"] = True
        self.store.touch("sparkles")
        self._gain_motif(now, sp["motif"])
        gained = self._award(now, "sparkle_collected")
        self._event(now, "motif", None, act, motif=sp["motif"], theme=sp["theme"], source="conversation", conversation_id=sp["conversation_id"], pulse=gained)

    # ---------------------------------------------------------------- building
    def agent_positions(self) -> dict[str, dict[str, Any]]:
        out = {}
        for aid in self.sim.order:
            st = self.sim.svc.states.get(aid)
            out[aid] = {"tile": tuple(st.tile) if st.tile else None, "path": [tuple(t) for t in (st.action.path or [])], "target": st.action.address}
        return out

    def validate_build(
        self,
        ops: list[dict[str, Any]],
        *,
        snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Check a batch of build operations without changing anything.

        ``snapshot`` (items, agents, requests, theme counts, level) lets the interface validate
        from another thread against the last published state; the engine re-validates every
        build when it applies it.
        """

        snap = snapshot or self.build_snapshot()
        placed = [PlacedItem.from_json(d) if isinstance(d, dict) else d for d in snap["items"]]
        agents = snap["agents"]
        by_id = {p.id: p for p in placed}
        drafts: list[Draft] = []
        removing: set[str] = set()
        problems: list[str] = []
        busy = {p.id for p in placed for a in agents.values() if a.get("target") == p.address}
        for op in ops:
            kind = op.get("op")
            if kind == "place":
                drafts.append(Draft(str(op.get("catalog_id")), int(op.get("x", 0)), int(op.get("y", 0)), int(op.get("rot", 0)) % 4, op.get("paint")))
            elif kind in ("move", "paint", "remove"):
                p = by_id.get(str(op.get("item_id")))
                if p is None:
                    problems.append(f"no placed item {op.get('item_id')}")
                    continue
                if kind == "move":
                    drafts.append(
                        Draft(p.catalog_id, int(op.get("x", p.x)), int(op.get("y", p.y)), int(op.get("rot", p.rot)) % 4, op.get("paint", p.paint), p.id)
                    )
                elif kind == "remove":
                    if p.id in busy:
                        problems.append(f"someone is using the {p.name} right now")
                    removing.add(p.id)
                elif kind == "paint":
                    try:
                        self.content.paint(str(op.get("paint")))
                    except KeyError:
                        problems.append(f"unknown paint {op.get('paint')}")
            else:
                problems.append(f"unknown build operation {kind!r}")
        verdicts = self.editor.validate(drafts, placed=placed, removing=removing, agents=agents, level=int(snap["level"]))
        cost: dict[str, int] = {}
        for d in drafts:
            if d.item_id is None:
                for t, n in self.content.item(d.catalog_id).cost.items():
                    cost[t] = cost.get(t, 0) + n
        refund: dict[str, int] = {}
        for rid in removing:
            for t, n in self.content.item(by_id[rid].catalog_id).cost.items():
                refund[t] = refund.get(t, 0) + n
        have = snap["counts"]
        net = {t: cost.get(t, 0) - refund.get(t, 0) for t in set(cost) | set(refund)}
        short = {t: n - have.get(t, 0) for t, n in net.items() if n > have.get(t, 0)}
        if short:
            problems.append("needs " + " and ".join(f"{n} more {self.content.theme(t).name} motif{'' if n == 1 else 's'}" for t, n in sorted(short.items())))
        return {
            "ok": not problems and all(v.ok for v in verdicts),
            "problems": problems,
            "verdicts": [v.to_json() for v in verdicts],
            "cost": cost,
            "refund": refund,
            "feedback": self.feedback(drafts, verdicts, placed, snap["requests"]),
        }

    def build_snapshot(self) -> dict[str, Any]:
        """What build validation needs, read on the engine thread."""

        return {
            "items": self.store.items(),
            "agents": self.agent_positions(),
            "requests": self.store.requests(),
            "counts": self.theme_counts(),
            "level": self.level(),
        }

    def feedback(self, drafts: list[Draft], verdicts: list[Any], items: list[PlacedItem], requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Affinity feedback for the player: the room's themes, who loves them, which requests fit."""

        out = []
        for d, v in zip(drafts, verdicts, strict=True):
            item = self.content.item(d.catalog_id)
            entry: dict[str, Any] = {"theme": item.theme, "arena": v.arena}
            if v.arena:
                room = self.aff.place_scores(v.arena)
                for p in items:
                    if p.address.rsplit(":", 1)[0] == v.arena:
                        room[self.content.item(p.catalog_id).theme] += 2.0
                entry["room_theme"] = self.aff.top(room)
                entry["harmony"] = bool(d.paint and self.content.paint(d.paint).theme == item.theme)
                entry["loved_by"] = [aid for aid, r in self.residents.items() if item.theme in r["loves"]]
                entry["fulfils"] = [r["id"] for r in requests if r["status"] == "open" and r["theme"] == item.theme and r["place_address"] == v.arena]
            out.append(entry)
        return out

    def _do_build(self, act: Action, now: datetime) -> None:
        ops = list(act.payload.get("ops") or [])
        if not ops:
            raise GameRuleError("nothing to build")
        check = self.validate_build(ops)
        if not check["ok"]:
            self._event(now, "build_rejected", None, act, problems=check["problems"], verdicts=check["verdicts"])
            return
        placed = {p.id: p for p in self.store.items()}
        net = {t: check["cost"].get(t, 0) - check["refund"].get(t, 0) for t in set(check["cost"]) | set(check["refund"])}
        spent = self._spend({t: n for t, n in net.items() if n > 0})
        self._refund({t: -n for t, n in net.items() if n < 0})
        taken: dict[str, set[str]] = {}
        made, moved, removed, painted = [], [], [], []
        verdicts = iter(check["verdicts"])
        for op in ops:
            kind = op["op"]
            if kind == "place":
                v = next(verdicts)
                item = self.content.item(op["catalog_id"])
                name = self.editor.unique_name(item.name, v["arena"], taken.setdefault(v["arena"], set()))
                taken[v["arena"]].add(name)
                p = PlacedItem(
                    id=self.store.next_id("item", "i"),
                    catalog_id=item.id,
                    name=name,
                    x=int(op["x"]),
                    y=int(op["y"]),
                    rot=int(op.get("rot", 0)) % 4,
                    paint=op.get("paint"),
                    address=f"{v['arena']}:{name}",
                    tiles=[tuple(t) for t in v["tiles"]],
                    blocks=item.blocks,
                    placed_at=iso(now),
                    step=self.sim.clock.step,
                )
                placed[p.id] = p
                made.append(p.id)
            elif kind == "move":
                v = next(verdicts)
                p = placed[op["item_id"]]
                old = p.address
                if v["arena"] != old.rsplit(":", 1)[0]:
                    p.name = self.editor.unique_name(self.content.item(p.catalog_id).name, v["arena"], taken.setdefault(v["arena"], set()))
                    taken[v["arena"]].add(p.name)
                    p.address = f"{v['arena']}:{p.name}"
                    self.sim.world_state.forget(old)
                p.x, p.y, p.rot = int(op.get("x", p.x)), int(op.get("y", p.y)), int(op.get("rot", p.rot)) % 4
                p.tiles = [tuple(t) for t in v["tiles"]]
                if "paint" in op:
                    p.paint = op["paint"]
                moved.append(p.id)
            elif kind == "paint":
                placed[op["item_id"]].paint = op["paint"]
                painted.append(op["item_id"])
            elif kind == "remove":
                p = placed.pop(op["item_id"])
                self.sim.world_state.forget(p.address)
                self.store.delete_item(p.id)
                removed.append(p.id)
        for p in placed.values():
            self.store.save_item(p, int(p.id.lstrip("i")))
        self.editor.apply(sorted(placed.values(), key=lambda p: p.id))
        gained = sum(self._award(now, "item_placed") for _ in made)
        self.store.get("stats")["items_placed"] += len(made)
        self.store.touch("stats")
        self._refresh_requests(now)
        self._event(
            now,
            "build",
            None,
            act,
            placed=[placed[i].to_json() for i in made],
            moved=[placed[i].to_json() for i in moved],
            removed=removed,
            painted=painted,
            spent=spent,
            refunded={t: -n for t, n in net.items() if n < 0},
            pulse=gained,
        )

    def _do_save_template(self, act: Action, now: datetime) -> None:
        name = " ".join(str(act.payload.get("name", "")).split())[:40]
        parts = act.payload.get("parts") or []
        if not name or not parts:
            raise GameRuleError("a template needs a name and at least one item")
        for part in parts:
            try:
                self.content.item(str(part.get("item")))
            except KeyError as exc:
                raise GameRuleError(str(exc)) from exc
        user = self.store.get("user_templates")
        tpl = {"id": f"u{len(user) + 1}", "name": name, "parts": [{k: part.get(k) for k in ("item", "dx", "dy", "rot", "paint")} for part in parts]}
        user.append(tpl)
        self.store.touch("user_templates")
        self._event(now, "template_saved", None, act, template=tpl)

    # ---------------------------------------------------------------- the paper's interventions
    def _do_object_state(self, act: Action, now: datetime) -> None:
        address = str(act.payload.get("address", ""))
        state = " ".join(str(act.payload.get("state", "")).split())[:60]
        if address.count(":") != 3 or not self.sim.world.exists(address):
            raise GameRuleError("unknown object")
        if not state:
            raise GameRuleError("describe the new state")
        self.sim.world_state.set_lasting(address, state, now, "intervention")
        self.sim.svc.events.log("intervention", now, None, kind="object_state", address=address, state=state, source="game", action_seq=act.seq)
        self._event(now, "object_state", None, act, address=address, state=state)

    def _do_whisper(self, act: Action, now: datetime) -> None:
        ident = self._resident(act.payload.get("agent", ""))
        text = " ".join(str(act.payload.get("text", "")).split())[:300]
        if not text:
            raise GameRuleError("whisper something")
        self.sim.svc.remember(ident, text, MemoryKind.OBSERVATION, MemoryOrigin.INNER_VOICE, now, metadata={"game_action": act.seq})
        self.sim.svc.events.log("intervention", now, ident.id, kind="inner_voice", text=text, source="game", action_seq=act.seq)
        self._event(now, "whisper", ident.id, act, text=text)

    # ================================================================== read model
    def state(self, now: datetime) -> dict[str, Any]:
        """Everything the player-facing interface shows (never sent to residents)."""

        pulse = self.store.get("pulse")
        level = self.content.level_for(int(pulse["points"]))
        nxt = next((lv for lv in self.content.levels if lv.level == level.level + 1), None)
        return {
            "pulse": {
                "points": int(pulse["points"]),
                "level": level.level,
                "name": level.name,
                "next_at": nxt.points if nxt else None,
                "next_name": nxt.name if nxt else None,
            },
            "inventory": dict(self.store.get("inventory")),
            "found": dict(self.store.get("found")),
            "theme_counts": self.theme_counts(),
            "friendship": {aid: int(self.store.get("friendship").get(aid, 0)) for aid in self.sim.order},
            "residents": {aid: {"loves": self.residents[aid]["loves"]} for aid in self.sim.order},
            "requests": self.store.requests(),
            "items": [p.to_json() for p in self.store.items()],
            "sparkles": self.visible_sparkles(now),
            "cooldowns": dict(self.store.get("cooldowns")),
            "user_templates": list(self.store.get("user_templates")),
            "stats": dict(self.store.get("stats")),
            "applied_seq": int(self.store.get("applied_seq")),
        }
