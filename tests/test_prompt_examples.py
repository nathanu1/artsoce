"""Per-task prompt examples from recorded ledgers (build prompt §2: input/output examples and raw-output traces)."""

from __future__ import annotations

import json
import os
import re

from generative_agents.config import GAConfig
from generative_agents.prompt_examples import write_prompt_examples
from generative_agents.prompting import PromptRegistry
from generative_agents.providers.gateway import GatewaySettings, LLMGateway
from generative_agents.providers.ledger import CallLedger
from generative_agents.providers.mock import ScriptedLLM
from generative_agents.simulation.budget import Budget

REGISTRY = PromptRegistry()


def make_run(path, run_id, script, *, settings=None):
    path.mkdir(parents=True)
    fidelity = json.loads(json.dumps(GAConfig().fidelity_table(), default=str))
    for row in fidelity:
        if row["setting"] in (settings or {}):
            row["value"] = settings[row["setting"]]
    (path / "manifest.json").write_text(json.dumps({"run_id": run_id, "mode": "mock", "label": "unit test (MOCK)", "fidelity": fidelity}))
    ledger = CallLedger(path / "provider.sqlite", scope=run_id)
    gw = LLMGateway(ScriptedLLM(script), REGISTRY, ledger, Budget(), GatewaySettings(model="m", max_validation_repairs=1, backoff_s=0), sleep=lambda s: None)
    return gw, ledger


def variables(task, **values):
    return {k: values.get(k, f"<{k}>") for k in REGISTRY.get(task).placeholders()}


def test_examples_show_exact_calls_repairs_and_their_source(tmp_path):
    gw, led = make_run(tmp_path / "a", "a", {"importance": ['{"rating": 42}', '{"rating": 4}', '{"rating": 2}', '{"rating": 3}']})
    gw.run("importance", variables("importance", memory="Isabella is planning a Valentine's Day party at Hobbs Cafe"), agent_id="i")
    gw.run("importance", variables("importance", memory="bed is idle"), agent_id="i")
    gw.run("importance", variables("importance", memory="an older call"), agent_id="i")
    rows = led.rows(task="importance")
    led.conn.execute("UPDATE calls SET template_hash='old' WHERE id=?", (rows[-1]["id"],))
    led.conn.commit()
    gw_b, led_b = make_run(
        tmp_path / "b", "b", {"seed_thought": [{"statement": "I want to host a party."}]}, settings={"scenario.seed_rendering": "inner_thought_llm"}
    )
    gw_b.run("seed_thought", variables("seed_thought"), agent_id="i")
    led.close(), led_b.close()

    out = tmp_path / "examples"
    res = write_prompt_examples([tmp_path / "a", tmp_path / "b"], out)
    assert set(res["tasks"]) == set(REGISTRY.tasks()) and res["tasks"]["importance"] == "a" and res["tasks"]["seed_thought"] == "b"
    assert "judge" in res["without_examples"] and "No successful call" in (out / "judge.md").read_text()

    page = (out / "importance.md").read_text()
    smallest = rows[2]  # "bed is idle": the shortest successful first attempt
    assert "## Smallest successful call" in page and smallest["prompt"] in page and f"Ledger call {smallest['id']}" in page
    assert "## A repaired call" in page and "Previous answer" in page and json.loads(rows[0]["validation_errors"])[0] in page
    assert "_1 call recorded with an earlier version of this template is not shown._" in page and "an older call" not in page
    link = re.search(r"\]\(([^)]+importance\.v1\.md)\)", page).group(1)
    assert os.path.exists(out / link)

    seed = (out / "seed_thought.md").read_text()
    assert "Example from run `b` (unit test (MOCK)), settings that differ from the defaults: `scenario.seed_rendering=inner_thought_llm`" in seed
    index = (out / "README.md").read_text()
    assert "**MOCK OUTPUTS.**" in index and "run `a` (unit test (MOCK)); default architecture settings" in index
    assert all(f"[{t}]({t}.md)" in index for t in REGISTRY.tasks())


def test_committed_examples_match_the_current_templates():
    # prompts/examples/ is generated; if a template changes, regenerate the examples (see their README).
    examples = REGISTRY.directory / "examples"
    assert (examples / "README.md").exists()
    for task in REGISTRY.tasks():
        tpl = REGISTRY.get(task)
        page = (examples / f"{task}.md").read_text()
        assert f"SHA-256 `{tpl.sha256}`" in page, f"prompts/examples/{task}.md is stale: regenerate it with ga prompt-examples"
        assert "## Smallest successful call" in page, f"prompts/examples/{task}.md has no example"
