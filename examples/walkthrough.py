"""From one conversation to a changed plan, with the real modules (offline, deterministic).

What the language model would *say* is scripted here so the example reads naturally and is
reproducible; everything else is the project's own code: how memories are stored and scored,
how retrieval normalizes and ranks them, how reflection validates its citations, and how
plans are validated and decomposed. Run it with:

    python examples/walkthrough.py
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from generative_agents.cognition.dialogue import DialogueEngine, Side
from generative_agents.cognition.planning import Planner, PlanStore
from generative_agents.cognition.reaction import ReactionEngine
from generative_agents.cognition.reflection import ReflectionEngine
from generative_agents.cognition.summary import SummaryService
from generative_agents.config import GAConfig, repo_path
from generative_agents.db import Database
from generative_agents.memory.evidence import evidence_tree
from generative_agents.memory.seeds import seed_agent
from generative_agents.memory.store import MemoryStore
from generative_agents.providers.embeddings import MockHashEmbedding
from generative_agents.providers.mock import MockLLM, ScriptedLLM
from generative_agents.scenario.loader import load_scenario
from generative_agents.schemas import MemoryKind, MemoryOrigin, PlanLevel
from generative_agents.simulation.runtime import build_runtime, make_services

MON_NOON = datetime(2023, 2, 13, 12, 10)


class WalkthroughLLM(ScriptedLLM):
    """Scripted words, but insights cite the numbered statements they are actually about."""

    def complete(self, request):  # type: ignore[override]
        if request.task == "reflection_insights":
            from generative_agents.providers.base import LLMResponse

            items = request.variables["_items"]
            party = [h for h, text in items if "party" in text.lower()]
            work = [h for h, text in items if "research paper" in text.lower()]
            out = []
            if party:
                out.append(
                    {"insight": "Klaus Mueller intends to go to Isabella Rodriguez's Valentine's Day party at Hobbs Cafe on February 14", "evidence": party[:3]}
                )
            if work:
                out.append({"insight": "Klaus Mueller is putting steady effort into his research paper", "evidence": work[:3]})
            self.calls.append(request)
            return LLMResponse(text=json.dumps({"insights": out}), input_tokens=10, output_tokens=10, served_model="scripted", tokens_estimated=True)
        return super().complete(request)


def show(title: str) -> None:
    print(f"\n=== {title} " + "=" * max(0, 74 - len(title)))


def main() -> None:
    cfg = GAConfig()
    sc = load_scenario(repo_path("scenarios/pilot5/scenario.yaml"), population=["isabella_rodriguez", "klaus_mueller"])
    isabella, klaus = sc.identities()["isabella_rodriguez"], sc.identities()["klaus_mueller"]
    db = Database(None)
    llm = WalkthroughLLM({}, fallback=MockLLM(seed=1))
    rt = build_runtime(cfg, store=MemoryStore(db), ledger_path=None, scope="walkthrough", provider=llm, embedding_provider=MockHashEmbedding(256))
    svc = make_services(cfg, db, rt, sc.identities())
    summary = SummaryService(svc)
    for spec in sc.agents.values():
        seed_agent(svc, spec, datetime(2023, 2, 13))

    show("1. A conversation (each line is its own model call, conditioned on the speaker's memories)")
    llm.script["dialogue_turn"] = [
        {
            "utterance": "Hi Klaus! I'm hosting a Valentine's Day party here at Hobbs Cafe tomorrow, February 14th, from 5 to 7 pm. Would you like to come?",
            "end_conversation": False,
        },
        {"utterance": "I'd love to come! Thanks for inviting me, Isabella.", "end_conversation": False},
        {"utterance": "Wonderful, see you there!", "end_conversation": True},
    ]
    llm.script["conversation_summary"] = [{"summary": "This is a conversation about Isabella inviting Klaus to her Valentine's Day party at Hobbs Cafe."}]
    llm.script["importance_batch"] = [
        {"ratings": [{"id": "1", "rating": 6}, {"id": "2", "rating": 4}, {"id": "3", "rating": 2}, {"id": "4", "rating": 5}]},
        {"ratings": [{"id": "1", "rating": 7}, {"id": "2", "rating": 5}, {"id": "3", "rating": 3}, {"id": "4", "rating": 6}]},
    ]
    conv = DialogueEngine(svc, summary, ReactionEngine(svc, summary)).run(
        Side(isabella, "Isabella Rodriguez is serving coffee at Hobbs Cafe", "Klaus Mueller is having lunch at Hobbs Cafe"),
        Side(klaus, "Klaus Mueller is having lunch at Hobbs Cafe", "Isabella Rodriguez is serving coffee at Hobbs Cafe"),
        MON_NOON,
        "the Ville:Hobbs Cafe:cafe",
    )
    for u in conv.utterances:
        print(f"  {sc.identities()[u.speaker_id].first_name}: {u.text}")
    print(f"  ({conv.metadata['minutes']} min; both agents' plans are revised from the end of the conversation)")

    show("2. What Klaus stored (only the two participants store the lines)")
    for m in svc.store.for_agent(klaus.id):
        if m.conversation_id == conv.id:
            print(f"  {m.id}  {m.origin.value:<13} importance {m.importance}  {m.description[:96]}")
    invite = next(m for m in svc.store.for_agent(klaus.id) if m.origin == MemoryOrigin.STATEMENT and "party" in m.description)
    state = svc.states.get(klaus.id)
    print(f"  reflection trigger (sum of importance of newly perceived memories): {state.reflection_accumulator:g} / {cfg.reflection.threshold:g}")

    show("3. Retrieval the next morning (scored before access times change)")
    tue = datetime(2023, 2, 14, 0, 0)
    for i in range(10):  # a quiet evening of ordinary observations
        svc.remember(
            klaus,
            f"Klaus Mueller is writing his research paper (part {i + 1})",
            MemoryKind.OBSERVATION,
            MemoryOrigin.EXECUTED_ACTION,
            MON_NOON + timedelta(hours=1, minutes=20 * i),
            importance=2,
        )
    res = svc.retriever.retrieve(
        klaus.id, "Important recent events for Klaus Mueller's life.", tue, max_items=5, budget_tokens=None, commit_access=False, purpose="walkthrough"
    )
    print(f"  query: {res.query!r}  ({len(res.candidates)} eligible memories)")
    for c in res.candidates[:5]:
        n = c.components(res.weights, res.mode)
        print(
            f"  #{c.rank} {c.score:.3f} = recency {n['recency']:.2f} + importance {n['importance']:.2f} + relevance {n['relevance']:.2f}  {c.memory.description[:70]}"
        )
    if invite.id in [c.memory.id for c in res.candidates[:5]]:
        other = next(c for c in res.candidates[:5] if c.memory.id != invite.id)
        ex = res.explain(invite.id, other.memory.id)
        print(f"  {ex['verdict']}")

    show("4. Reflection (questions → retrieval → insights that must cite what they were shown)")
    llm.script["reflection_questions"] = [
        {
            "questions": [
                "What is Klaus Mueller looking forward to?",
                "How does Klaus Mueller feel about Isabella Rodriguez?",
                "What is Klaus Mueller working on?",
            ]
        }
    ]

    state.reflection_accumulator = 151  # pretend the evening's perceptions crossed the threshold
    report = ReflectionEngine(svc).run(klaus, tue)
    party = [i for i in report["insights"] if "party" in i["text"]]
    if party:
        ins = party[0]
        q = next(q["question"] for q in report["questions"] if ins["id"] in q["insight_ids"])
        print(f"  question: {q}")
        print(f"  insight {ins['id']} (depth {ins['depth']}): {ins['text']}")
        tree = evidence_tree(svc.store, ins["id"])
        for e in tree["evidence"]:
            print(f"    cites {e['id']} [{e['kind']}]: {e['description'][:90]}")
    print(
        f"  stored {report['stored']} insight(s) in total; rejected citations: {len([f for f in report['failures'] if 'rejected' in f])}; trigger reset to {state.reflection_accumulator:g}"
    )
    print("  (citations are checked for existence, ownership, having been shown, and cycles, not for whether they support the claim)")

    show("5. Tuesday's plan (day plan → hour blocks → 5–15 minute tasks just in time)")
    llm.script["previous_day"] = [
        {
            "summary": "On Monday Klaus worked on his gentrification paper at the library, and at lunch Isabella invited him to her Valentine's Day party at Hobbs Cafe on February 14 from 5 to 7 pm, which he accepted."
        }
    ]
    llm.script["day_plan"] = [
        {
            "wake_up_time": "07:00",
            "items": [
                {"time": "07:00", "activity": "wake up and complete the morning routine"},
                {"time": "08:00", "activity": "work on his research paper at the library"},
                {"time": "12:00", "activity": "have lunch at Hobbs Cafe"},
                {"time": "13:00", "activity": "keep writing his research paper at the library"},
                {"time": "17:00", "activity": "go to Isabella's Valentine's Day party at Hobbs Cafe"},
                {"time": "19:00", "activity": "have dinner"},
                {"time": "23:00", "activity": "go to bed"},
            ],
        }
    ]
    state.plan_day = "2023-02-13"
    plans = PlanStore(db)
    planner = Planner(svc, summary, plans)
    planner.ensure_day(klaus, tue)
    print(f"  previous day: {state.previous_day_summary}")
    for b in plans.items(klaus.id, day="2023-02-14", level=PlanLevel.HOUR):
        print(f"  {b.start:%H:%M}–{b.end:%H:%M}  {b.description}")
    task = planner.current_task(klaus, datetime(2023, 2, 14, 17, 5))
    print(f"  at 17:05 the current task is: {task.description} ({task.start:%H:%M}, {task.duration_min} min)")
    calls = rt.ledger.totals()
    print(
        f"\n{calls['calls']} model calls recorded in the ledger ({len(llm.calls)} answered; scripted where the walkthrough needs specific words, otherwise the offline mock)."
    )
    print(json.dumps({"scripted_tasks": sorted(k for k in llm.script)}, indent=None))


if __name__ == "__main__":
    main()
