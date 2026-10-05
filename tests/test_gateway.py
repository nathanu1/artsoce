"""Provider gateway: validation, bounded repairs, retries, budgets, cache scope, replay (spec O-1 … O-3, D-4)."""

from __future__ import annotations

from datetime import datetime

import pytest

from generative_agents.cognition.importance import ImportanceScorer
from generative_agents.config import GAConfig
from generative_agents.prompting import PromptRegistry
from generative_agents.providers.base import (
    BudgetExceeded,
    LLMRequest,
    ProviderError,
    ReplayMiss,
    TaskFailed,
)
from generative_agents.providers.gateway import GatewaySettings, LLMGateway, extract_json
from generative_agents.providers.ledger import CallLedger
from generative_agents.providers.mock import MockLLM, ScriptedLLM, chunk_minutes
from generative_agents.providers.schema import strict_json_schema
from generative_agents.schemas import AgentIdentity
from generative_agents.simulation.budget import Budget

NOW = datetime(2023, 2, 13, 9, 0)
IDENT = AgentIdentity(
    id="isabella_rodriguez", name="Isabella Rodriguez", first_name="Isabella", last_name="Rodriguez", age=34,
    innate="friendly, outgoing, hospitable", learned="Isabella Rodriguez is a cafe owner of Hobbs Cafe.",
    currently="Isabella is planning a party.", lifestyle="goes to bed around 11pm, awakes up around 6am.",
    living_area="the Ville:Isabella Rodriguez's apartment:main room",
)


def make_gateway(provider, *, budget=None, ledger=None, repairs=1, retries=2, replay=False):
    return LLMGateway(
        provider, PromptRegistry(), ledger or CallLedger(None, scope="run-1"), budget or Budget(),
        GatewaySettings(model="m", max_retries=retries, max_validation_repairs=repairs, backoff_s=0),
        replay=replay, sleep=lambda s: None,
    )


def imp_vars(text="Isabella is planning a Valentine's Day party"):
    return {"agent_name": "Isabella", "agent_summary": "s", "mundane_examples": "x", "poignant_examples": "y",
            "kind_label": "memory", "kind_title": "Memory", "memory": text, "_memory": text}


def test_every_template_renders_and_has_a_strict_schema():
    reg = PromptRegistry()
    assert {"importance", "reflection_questions", "reflection_insights", "day_plan", "hourly_schedule", "decompose",
            "replan", "choose_location", "action_grounding", "interaction_context", "reaction", "dialogue_turn",
            "conversation_summary", "interview", "summary_aspect"} <= set(reg.tasks())
    for task in reg.tasks():
        tpl = reg.get(task)
        assert tpl.source and tpl.scope, f"{task} must state its source and information scope"
        schema = strict_json_schema(tpl.output_model)
        assert schema["additionalProperties"] is False
        system, user = tpl.render({k: f"<{k}>" for k in tpl.placeholders()})
        assert "{{" not in user and "{{" not in system
    with pytest.raises(KeyError):
        reg.get("importance").render({})


def test_extract_json_tolerates_fences():
    assert extract_json('```json\n{"rating": 3}\n```') == {"rating": 3}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_valid_output_is_recorded_once_and_ok():
    gw = make_gateway(ScriptedLLM({"importance": [{"rating": 7}]}))
    res = gw.run("importance", imp_vars(), agent_id="a", sim_time=NOW)
    assert res.output.rating == 7 and not res.cached
    rows = gw.ledger.rows()
    assert len(rows) == 1 and rows[0]["status"] == "ok" and rows[0]["template_id"] == "importance@v1"


def test_invalid_output_is_repaired_with_bounded_attempts():
    gw = make_gateway(ScriptedLLM({"importance": ['{"rating": 42}', '{"rating": 4}']}))
    res = gw.run("importance", imp_vars(), agent_id="a")
    assert res.output.rating == 4 and len(res.call_ids) == 2
    statuses = [r["status"] for r in gw.ledger.rows()]
    assert statuses == ["invalid", "ok"]
    assert "Previous answer" in gw.ledger.rows()[1]["prompt"]


def test_repairs_exhausted_raises_instead_of_fabricating():
    gw = make_gateway(ScriptedLLM({"importance": ["not json", '{"rating": 0}']}), repairs=1)
    with pytest.raises(TaskFailed) as err:
        gw.run("importance", imp_vars(), agent_id="a")
    assert len(err.value.call_ids) == 2 and err.value.errors


def test_semantic_validator_drives_repair():
    gw = make_gateway(ScriptedLLM({"choose_location": [{"choice": "Mars"}, {"choice": "Hobbs Cafe"}]}))
    v = {"agent_summary": "s", "agent_name": "I", "current_place": "x", "current_children": "", "level_plural": "areas",
         "options": "Hobbs Cafe, Johnson Park", "level": "area", "activity": "work"}
    res = gw.run("choose_location", v, validate=lambda o: [] if o.choice in ("Hobbs Cafe", "Johnson Park") else ["not an option"])
    assert res.output.choice == "Hobbs Cafe"


def test_transient_errors_are_retried_then_succeed():
    gw = make_gateway(ScriptedLLM({"importance": [ProviderError("503", retryable=True), {"rating": 5}]}), retries=2)
    assert gw.run("importance", imp_vars()).output.rating == 5
    assert [r["status"] for r in gw.ledger.rows()] == ["error", "ok"]


def test_non_retryable_error_propagates():
    gw = make_gateway(ScriptedLLM({"importance": [ProviderError("400 bad request", retryable=False)]}))
    with pytest.raises(ProviderError):
        gw.run("importance", imp_vars())


def test_budget_ceiling_stops_before_the_call():
    budget = Budget(max_calls=1)
    gw = make_gateway(MockLLM(), budget=budget)
    gw.run("importance", imp_vars("one"))
    with pytest.raises(BudgetExceeded):
        gw.run("importance", imp_vars("two"))
    assert budget.usage.calls == 1 and len(gw.ledger.rows()) == 1


def test_exact_repeats_are_occurrence_indexed_and_resume_reuses_rolled_back_calls():
    ledger = CallLedger(None, scope="run-1")
    provider = ScriptedLLM({"importance": [{"rating": 2}, {"rating": 9}]})
    gw = make_gateway(provider, ledger=ledger)
    gw.step_getter = lambda: 5
    a = gw.run("importance", imp_vars("same text"))
    b = gw.run("importance", imp_vars("same text"))
    assert (a.output.rating, b.output.rating) == (2, 9)  # identical requests are not collapsed
    # Simulate a crash after step 4 committed: re-executing step 5 reuses the recorded calls.
    ledger.reset_counts(committed_step=4)
    gw2 = make_gateway(ScriptedLLM({}), ledger=ledger)
    assert gw2.run("importance", imp_vars("same text")).cached
    assert [gw2.run("importance", imp_vars("same text")).output.rating] == [9]


def test_cache_scope_isolates_independent_runs():
    path = None
    l1 = CallLedger(path, scope="run-A")
    gw1 = make_gateway(ScriptedLLM({"importance": [{"rating": 3}]}), ledger=l1)
    gw1.run("importance", imp_vars())
    l1.scope = "run-B"  # a different replicate must not see run-A's samples
    l1.reset_counts(None)
    gw2 = make_gateway(ScriptedLLM({"importance": [{"rating": 8}]}), ledger=l1)
    assert gw2.run("importance", imp_vars()).output.rating == 8


def test_replay_never_calls_a_model():
    ledger = CallLedger(None, scope="src")
    make_gateway(MockLLM(), ledger=ledger).run("importance", imp_vars())
    ledger.readonly_scope = "src"
    ledger.reset_counts(None)
    replayer = ScriptedLLM({})
    gw = make_gateway(replayer, ledger=ledger, replay=True)
    assert gw.run("importance", imp_vars()).cached
    with pytest.raises(ReplayMiss):
        gw.run("importance", imp_vars("never recorded"))
    assert replayer.calls == []


def test_importance_idle_shortcut_and_range():
    gw = make_gateway(MockLLM())
    scorer = ImportanceScorer(gw)
    assert scorer.score(IDENT, "desk is idle", "observation", NOW) == 1
    assert gw.ledger.rows() == []  # no call for idle memories
    r = scorer.score(IDENT, "Isabella is planning a Valentine's Day party", "observation", NOW)
    assert 1 <= r <= 10


def test_importance_batch_requires_one_rating_per_item():
    gw = make_gateway(ScriptedLLM({"importance_batch": [
        {"ratings": [{"id": "1", "rating": 3}]},
        {"ratings": [{"id": "1", "rating": 3}, {"id": "2", "rating": 8}]},
    ]}))
    assert ImportanceScorer(gw).score_batch(IDENT, ["hello", "you're invited"], NOW) == [3, 8]


def test_mock_provider_is_deterministic():
    req = LLMRequest(task="importance", template_id="importance@v1", template_hash="h", system="s", prompt="p",
                     output_schema={}, model="mock", max_output_tokens=10, variables={"_memory": "planning a party"})
    assert MockLLM(seed=1).complete(req).text == MockLLM(seed=1).complete(req).text


def test_chunking_respects_bounds():
    for total in (5, 7, 15, 16, 30, 45, 60, 61, 90, 125):
        parts = chunk_minutes(total, 5, 15)
        assert sum(parts) == total and all(5 <= p <= 15 for p in parts)


def test_config_defaults_match_registry():
    cfg = GAConfig()
    table = {r["setting"]: r for r in cfg.fidelity_table()}
    assert table["retrieval.mode"]["value"] == "paper" and table["retrieval.mode"]["class"] == "P"
    assert table["reflection.threshold"]["value"] == 150.0
    assert table["clock.seconds_per_step"]["value"] == 10
