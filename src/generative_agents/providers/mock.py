"""Deterministic offline stand-in for a language model (a TEST FIXTURE, not a research tool).

``MockLLM`` returns schema-valid JSON for every task so the whole pipeline (memory,
reflection, planning, movement, dialogue, evaluation) can run without credentials. It reads
the structured ``request.variables`` (keys beginning with ``_``) that callers pass next to
the rendered prompt, and applies simple keyword rules plus a seeded hash for variety.

Its "behavior" (e.g. sharing news it finds in the speaker's own retrieved memories) only
exercises information flow through the architecture. Runs that use it are labeled MOCK
everywhere; their outcomes are structural demonstrations, never evidence about the paper.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections import Counter
from typing import Any

from .base import LLMRequest, LLMResponse, ProviderError, estimate_tokens

HIGH_WORDS = ("party", "valentine", "invite", "mayor", "election", "running for", "crush", "love", "date", "fire", "burning")
MED_WORDS = ("said", "conversation", "talk", "friend", "plan", "research", "paper", "exam", "class", "show")
NEGATIONS = ("not sure", "don't know", "do not know", "no idea", "haven't heard", "have not heard", "don't remember", "do not remember", "not aware")

LOCATION_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (("sleep", "bed", "nap", "asleep"), ("bed", "{home}", "main room")),
    (("party", "cafe", "coffee", "counter", "pastr", "barista", "customers"), ("Hobbs Cafe", "cafe", "behind the cafe counter", "cafe customer seating")),
    (("library", "research", "paper", "read", "study", "studying", "exam", "notes"), ("Oak Hill College", "library", "library table", "{home}")),
    (("class", "lecture", "teach", "seminar"), ("Oak Hill College", "classroom", "classroom student seating")),
    (("park", "walk", "garden", "run", "jog", "stroll"), ("Johnson Park", "park", "park garden")),
    (("grocer", "pharmac", "medicine", "shopping", "store"), ("The Willows Market and Pharmacy", "store", "grocery store shelf")),
    (("supplies", "supply", "material", "decorat"), ("Harvey Oak Supply Store", "supply store", "supply store product shelf")),
    (("bar", "pub", "drink", "beer"), ("The Rose and Crown Pub", "pub", "bar customer seating")),
    (("stream", "twitch", "game", "computer", "email", "laptop"), ("{home}", "{room}", "computer", "desk")),
    (("cook", "kitchen", "breakfast", "lunch", "dinner", "meal", "eat"), ("{home}", "kitchen", "cooking area", "main room", "common room", "refrigerator")),
    (("shower", "bath", "teeth", "toilet", "wash"), ("{home}", "bathroom", "shower", "bathroom sink")),
    (("routine", "dress", "wake"), ("{home}", "{room}", "main room", "closet", "bed")),
]


def _seed(*parts: Any) -> random.Random:
    h = hashlib.sha256("␟".join(str(p) for p in parts).encode()).digest()
    return random.Random(int.from_bytes(h[:8], "little"))


def _hhmm(minutes: int) -> str:
    minutes = max(0, min(24 * 60, minutes))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _parse_hour(text: str, default: int) -> int:
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", text.lower())
    if not m:
        return default
    hour = int(m.group(1)) % 12
    if m.group(3) == "pm":
        hour += 12
    return hour * 60 + int(m.group(2) or 0)


def _first_person(text: str) -> str:
    s = re.sub(r"\*", "", text).strip()
    s = re.sub(r"\bYou are\b", "I am", s)
    s = re.sub(r"\byou are\b", "I am", s)
    s = re.sub(r"\bYou\b", "I", s)
    s = re.sub(r"\byour\b", "my", s)
    s = re.sub(r"\byou\b", "me", s)
    return s.rstrip(".")


def chunk_minutes(total: int, lo: int, hi: int) -> list[int]:
    """Split ``total`` into near-equal parts within [lo, hi] (a single part if total < lo)."""

    if total <= hi:
        return [total]
    n = math.ceil(total / hi)
    base, extra = divmod(total, n)
    parts = [base + (1 if i < extra else 0) for i in range(n)]
    if min(parts) < lo:
        return [total]
    return parts


class MockLLM:
    name = "mock"

    def __init__(self, seed: int = 0, model: str = "mock-llm-v1", fail_tasks: dict[str, int] | None = None):
        self.seed = seed
        self.model = model
        self.fail_tasks = dict(fail_tasks or {})  # task -> number of transient failures to inject

    def describe(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "fixture": True, "seed": self.seed}

    def complete(self, request: LLMRequest) -> LLMResponse:
        if self.fail_tasks.get(request.task, 0) > 0:
            self.fail_tasks[request.task] -= 1
            raise ProviderError("injected transient failure", retryable=True)
        handler = getattr(self, f"_t_{request.task}", None)
        if handler is None:
            raise ProviderError(f"mock has no handler for task {request.task}", retryable=False)
        rng = _seed(self.seed, request.task, request.prompt)
        out = handler(request.variables, rng)
        text = json.dumps(out, ensure_ascii=False)
        return LLMResponse(
            text=text,
            input_tokens=estimate_tokens(request.system + request.prompt),
            output_tokens=estimate_tokens(text),
            served_model=self.model,
            tokens_estimated=True,
        )

    # ------------------------------------------------------------------ memory tasks
    @staticmethod
    def _rate(text: str, rng: random.Random) -> int:
        t = text.lower()
        if t.rstrip(". ").endswith("is idle"):
            return 1
        if any(w in t for w in HIGH_WORDS):
            return rng.randint(6, 9)
        if any(w in t for w in MED_WORDS):
            return rng.randint(3, 6)
        return rng.randint(1, 4)

    def _t_importance(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        return {"rating": self._rate(v.get("_memory", v.get("memory", "")), rng)}

    def _t_importance_batch(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        return {"ratings": [{"id": str(i), "rating": self._rate(t, rng)} for i, t in v["_items"]]}

    def _t_summary_aspect(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        stmts = [s for s in v.get("_statements", []) if s]
        name = v.get("_name", "The agent")
        lead = {"core": f"{name} is {v.get('_traits', 'a resident of the town')}.",
                "occupation": f"{name} spends the day on the usual routine.",
                "feeling": f"{name} feels steady about recent progress."}.get(v.get("_aspect", "core"), f"{name}.")
        if stmts:
            lead += " Notably: " + "; ".join(s.rstrip(".") for s in stmts[:2]) + "."
        return {"summary": lead}

    def _t_previous_day(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        stmts = v.get("_statements", [])
        name = v.get("_name", "The agent")
        sched = [s for s in stmts if re.search(r"party|february|pm|am|tomorrow|meet", s, re.I)]
        body = f"{name} followed their routine on {v.get('_yesterday', 'the previous day')}."
        if sched:
            body += " To remember: " + "; ".join(s.rstrip(".") for s in sched[:2]) + "."
        return {"summary": body}

    def _t_reflection_questions(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        n = int(v.get("_n", 3))
        name = v.get("_name", "the agent")
        text = " ".join(v.get("_statements", []))
        others = [p for p, _ in Counter(re.findall(r"\b([A-Z][a-z]+ [A-Z][a-z]+)\b", text)).most_common() if p != name]
        words = [w for w, _ in Counter(w for w in re.findall(r"[a-z]{5,}", text.lower()) if w not in {"about", "their", "there", "which", "would"}).most_common(6)]
        qs = [f"What is {name} most focused on lately?"]
        if others:
            qs.append(f"What is the relationship between {name} and {others[0]}?")
        if words:
            qs.append(f"What does {name} think about {words[0]}?")
        while len(qs) < n:
            qs.append(f"What matters most to {name} right now? ({len(qs) + 1})")
        return {"questions": qs[:n]}

    def _t_reflection_insights(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        items: list[tuple[str, str]] = v["_items"]
        n = int(v.get("_n", 5))
        name = v.get("_name", "the agent")
        if not items:
            return {"insights": []}
        out = []
        for k in range(min(n, max(1, len(items) // 2))):
            cited = rng.sample(items, k=min(len(items), rng.randint(1, 3)))
            words = [w for w in re.findall(r"[a-z]{5,}", " ".join(t for _, t in cited).lower())]
            topic = words[k % len(words)] if words else "daily life"
            out.append({"insight": f"{name} seems to care about {topic}", "evidence": [h for h, _ in cited]})
        return {"insights": out}

    # ------------------------------------------------------------------ planning tasks
    def _t_day_plan(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        ident = v["_identity"]
        lifestyle = ident.get("lifestyle", "")
        wake = _parse_hour(lifestyle.split("awake")[-1] if "awake" in lifestyle else "7am", 7 * 60)
        bed = _parse_hour(lifestyle.split("bed")[-1] if "bed" in lifestyle else "11pm", 23 * 60)
        if bed <= wake:
            bed = 23 * 60
        routine = (ident.get("daily_plan_req") or ident.get("currently") or "go about the day").rstrip(".")
        work = f"spend time on the daily routine: {routine[0].lower() + routine[1:] if routine else 'errands'}"
        items = [(wake, "wake up and complete the morning routine"), (wake + 60, "have breakfast")]
        items.append((max(wake + 120, 9 * 60), work))
        items.append((12 * 60, "have lunch"))
        items.append((13 * 60, work))
        knowledge = (v.get("_knowledge") or "").lower()
        day = v.get("_day_label", "")
        if "february 14" in day.lower() and "party" in knowledge and ("hobbs cafe" in knowledge or "cafe" in knowledge):
            items.append((17 * 60, "go to the Valentine's Day party at Hobbs Cafe"))
            items.append((19 * 60, "have dinner"))
        else:
            items.append((18 * 60, "have dinner"))
        if bed - 60 > items[-1][0]:
            items.append((bed - 60, "relax and wind down"))
        items.append((bed, "go to bed"))
        items = sorted({t: a for t, a in items}.items())
        return {"wake_up_time": _hhmm(wake), "items": [{"time": _hhmm(t), "activity": a} for t, a in items]}

    def _t_hourly_schedule(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        items: list[tuple[int, str]] = sorted(v["_items"])
        blocks = []
        cursor = 0
        if items and items[0][0] > 0:
            blocks.append((0, items[0][0], "sleeping"))
            cursor = items[0][0]
        for i, (t, act) in enumerate(items):
            end = items[i + 1][0] if i + 1 < len(items) else 24 * 60
            if "go to bed" in act or act.startswith("sleep"):
                blocks.append((t, min(t + 30, end), act))
                if end > t + 30:
                    blocks.append((t + 30, end, "sleeping"))
            else:
                blocks.append((t, end, act))
            cursor = end
        if cursor < 24 * 60:
            blocks.append((cursor, 24 * 60, "sleeping"))
        merged: list[list[Any]] = []
        for s, e, a in blocks:
            if e <= s:
                continue
            if merged and merged[-1][2] == a and merged[-1][1] == s:
                merged[-1][1] = e
            else:
                merged.append([s, e, a])
        return {"blocks": [{"start": _hhmm(s), "end": _hhmm(e), "activity": a} for s, e, a in merged]}

    def _t_decompose(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        total = int(v["_duration"])
        start = int(v["_start_min"])
        act = v["_activity"]
        parts = chunk_minutes(total, int(v.get("_min", 5)), int(v.get("_max", 15)))
        labels = ["getting started", "focused on it", "continuing", "making progress", "taking a short break", "wrapping up"]
        tasks, t = [], start
        for i, d in enumerate(parts):
            label = labels[0] if i == 0 else (labels[-1] if i == len(parts) - 1 else labels[1 + (i % 4)])
            tasks.append({"start": _hhmm(t), "duration_minutes": d, "activity": f"{act} ({label})" if len(parts) > 1 else act})
            t += d
        return {"tasks": tasks}

    def _t_replan(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        start = int(v["_resume_min"])
        remaining = int(v["_remaining"])
        original: list[tuple[int, int, str]] = v.get("_original", [])
        later = [a for s, d, a in original if s + d > start] or ["continue the day"]
        parts = chunk_minutes(remaining, int(v.get("_min", 5)), int(v.get("_max", 15))) if remaining > 0 else []
        tasks, t = [], start
        for i, d in enumerate(parts):
            tasks.append({"start": _hhmm(t), "duration_minutes": d, "activity": later[min(i, len(later) - 1)]})
            t += d
        return {"tasks": tasks}

    # ------------------------------------------------------------------ grounding tasks
    def _t_choose_location(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        options: list[str] = v["_options"]
        act = v.get("_activity", "").lower()
        home = v.get("_home", "")
        room = v.get("_room", "")
        current = v.get("_current")
        for keys, targets in LOCATION_RULES:
            if any(k in act for k in keys):
                for target in targets:
                    target = target.replace("{home}", home).replace("{room}", room)
                    if not target:
                        continue
                    for opt in options:
                        if target.lower() == opt.lower() or (len(target) > 3 and target.lower() in opt.lower()):
                            return {"choice": opt}
                break
        if current and current in options:
            return {"choice": current}
        if home and home in options:
            return {"choice": home}
        return {"choice": sorted(options)[rng.randrange(len(options))]}

    def _t_action_grounding(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        name = v["_name"]
        act = v["_activity"].lower()
        obj = v.get("_object", "").lower()
        if re.search(r"turn(ing)? off|put(ting)? out", act):
            state = "turned off"
        elif "coffee" in obj and ("coffee" in act or "serv" in act or "brew" in act):
            state = "brewing coffee"
        elif any(k in obj for k in ("stove", "cooking")) and any(k in act for k in ("cook", "breakfast", "dinner", "lunch")):
            state = "being used to cook"
        elif "bed" in obj and "sleep" in act:
            state = "being slept in"
        elif any(k in obj for k in ("shower", "toilet", "bathroom")):
            state = "occupied"
        elif "refrigerator" in obj:
            state = "being opened"
        elif obj:
            state = "being used"
        else:
            state = "idle"
        words = re.sub(r"\(.*?\)", "", v["_activity"]).strip().split()
        return {"subject": name, "predicate": "is", "object": " ".join(words[:6]) or "busy", "object_state": state}

    # ------------------------------------------------------------------ social tasks
    def _t_interaction_context(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        observer, observed = v["_observer"], v["_observed"]
        first = observed.split()[0]
        about = [s for s in v.get("_statements", []) if first in s]
        if about:
            body = f"{observer} knows {observed}: " + about[0].rstrip(".") + "."
        else:
            body = f"{observer} does not know {observed} well."
        status = v.get("_observed_status")
        if status:
            body += f" {observed} is {status}."
        return {"summary": body}

    def _t_reaction(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        obs = v.get("_observation", "").lower()
        if not v.get("_observed_is_agent"):
            if re.search(r"burning|fire|smok", obs):
                return {"decision": "react", "reason": "Something is burning.", "new_activity": "turn off the stove and deal with the smoke" if "stove" in obs else "alert others about the fire and stay safe", "duration_minutes": 10}
            if "leak" in obs:
                return {"decision": "react", "reason": "There is a leak.", "new_activity": "fix the leak", "duration_minutes": 15}
            if "empty" in obs and "refrigerator" in obs:
                return {"decision": "react", "reason": "No food at home.", "new_activity": "go buy groceries at The Willows Market and Pharmacy", "duration_minutes": 45}
            if re.search(r"occupied|in use|closed", obs):
                return {"decision": "wait", "reason": "It is not available right now.", "new_activity": None, "duration_minutes": 5}
            return {"decision": "continue", "reason": "Nothing needs attention.", "new_activity": None, "duration_minutes": None}
        if not v.get("_can_talk"):
            return {"decision": "continue", "reason": "Not a good moment to talk.", "new_activity": None, "duration_minutes": None}
        p = 0.12
        if v.get("_knows_observed"):
            p += 0.25
        if v.get("_has_news"):
            p += 0.35
        if rng.random() < p:
            return {"decision": "talk", "reason": "They know each other and have something to say.", "new_activity": None, "duration_minutes": None}
        return {"decision": "continue", "reason": "Busy with the current activity.", "new_activity": None, "duration_minutes": None}

    def _t_dialogue_turn(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        speaker, partner = v["_speaker"], v["_partner"]
        idx = int(v.get("_turn_index", 0))
        news: list[str] = v.get("_news", [])
        heard: str = v.get("_transcript_text", "")
        pfirst = partner.split()[0]
        limit = 4 + _seed(self.seed, speaker, partner, v.get("_conversation_id", "")).randint(0, 4)
        if idx == 0:
            text = f"Hi {pfirst}!"
            if news:
                text += f" Did you hear? {_first_person(news[0])}."
                if "party" in news[0].lower():
                    text += " You should come!"
            else:
                text += " How is your day going?"
            return {"utterance": text, "end_conversation": False}
        last = v.get("_last_utterance", "").lower()
        fresh = [n for n in news if _first_person(n)[:40].lower() not in heard.lower()]
        if "party" in last and ("come" in last or "join" in last or "invit" in last):
            text = "That sounds wonderful, I'd love to come to the party!"
        elif fresh and idx < limit - 1:
            text = f"Oh, also: {_first_person(fresh[0])}."
        elif idx >= limit - 1:
            return {"utterance": f"It was good talking to you, {pfirst}. See you around!", "end_conversation": True}
        else:
            text = rng.choice(["That's interesting.", "I see, thanks for telling me.", "Good to know!", "Glad to hear it."])
        return {"utterance": text, "end_conversation": idx >= limit}

    def _t_conversation_summary(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        t = v.get("_transcript_text", "").lower()
        if "party" in t:
            topic = "a Valentine's Day party"
        elif "mayor" in t or "election" in t:
            topic = "the local mayor election"
        else:
            topic = "how their days are going"
        return {"summary": f"This is a conversation about {topic}."}

    def _t_conversation_inferences(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        t = v.get("_transcript_text", "")
        name = v.get("_name", "The agent")
        note = None
        if "party" in t.lower():
            note = f"{name} should remember the Valentine's Day party at Hobbs Cafe."
        return {"planning_note": note, "memo": f"{name} found the conversation pleasant." if t else None}

    def _t_interview(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        q = v.get("_question", "").lower()
        stmts: list[str] = v.get("_statements", [])
        keys = [w for w in re.findall(r"[a-z]{4,}", q) if w not in {"what", "would", "your", "with", "will", "have", "there", "today", "doing"}]
        hits = [s for s in stmts if any(k in s.lower() for k in keys)]
        if hits:
            return {"answer": "From what I remember, " + _first_person(hits[0])[0].lower() + _first_person(hits[0])[1:] + "."}
        if not stmts:
            return {"answer": "I'm not sure; I don't remember anything about that."}
        return {"answer": "I'm not sure about that."}

    def _t_awareness(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        ans = v.get("_answer", "").lower()
        keys = [k.lower() for k in v.get("_topic_keywords", [])]
        knows = any(k in ans for k in keys) and not any(n in ans for n in NEGATIONS)
        details = [d for d, pats in v.get("_detail_patterns", {}).items() if any(re.search(p, ans, re.I) for p in pats)] if knows else []
        return {"claims_knowledge": knows, "details": details, "quote": v.get("_answer", "")[:120] if knows else ""}

    def _t_seed_thought(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        name = v["_name"]
        s = v["_thought"].replace("*", "").strip()
        s = re.sub(r"^You are\b", f"{name} is", s)
        s = re.sub(r"^You\b", name, s)
        s = re.sub(r"\byour\b", "their", s)
        s = re.sub(r"\byou\b", name.split()[0], s)
        return {"statement": s}

    def _t_judge(self, v: dict[str, Any], rng: random.Random) -> dict[str, Any]:
        ans = v.get("_answer", "")
        return {"score": max(1, min(7, 2 + len(ans) // 80)), "rationale": "Mock heuristic based on answer length."}


class ScriptedLLM:
    """Test helper: returns queued raw outputs per task (to exercise repairs and failures)."""

    name = "scripted"

    def __init__(self, script: dict[str, list[Any]], fallback: MockLLM | None = None):
        self.script = {k: list(v) for k, v in script.items()}
        self.fallback = fallback
        self.calls: list[LLMRequest] = []

    def describe(self) -> dict[str, Any]:
        return {"provider": self.name, "model": "scripted", "fixture": True}

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        queue = self.script.get(request.task)
        if queue:
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            text = item if isinstance(item, str) else json.dumps(item)
            return LLMResponse(text=text, input_tokens=10, output_tokens=10, served_model="scripted", tokens_estimated=True)
        if self.fallback is not None:
            return self.fallback.complete(request)
        raise ProviderError(f"script exhausted for task {request.task}", retryable=False)
