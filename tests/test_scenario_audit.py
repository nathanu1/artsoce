"""Full 25-agent scenario audit and import reproducibility (spec A-1 … A-6, J-8)."""

from __future__ import annotations

import filecmp
from pathlib import Path

import pytest

from generative_agents.config import repo_path
from generative_agents.scenario.audit import audit_scenario
from generative_agents.scenario.importer import import_official
from generative_agents.scenario.loader import load_scenario

OFFICIAL = Path("/home/user/joonspk-research/generative_agents")
N25 = repo_path("scenarios/smallville_n25/scenario.yaml")


def test_n25_audit_is_clean_under_the_paper_policy():
    rep = audit_scenario(load_scenario(N25))
    assert rep["ok"], rep["issues"]
    assert rep["agents"] == 25 and rep["unique_ids"] and rep["unique_names"]
    assert [h["agent"] for h in rep["knowledge_holders"]["party_knowledge"]] == ["isabella_rodriguez"]
    assert [h["agent"] for h in rep["knowledge_holders"]["candidacy_knowledge"]] == ["sam_moore"]
    assert all(v["perception"] == {"vision_r": 8, "att_bandwidth": 8, "retention": 8} for v in rep["per_agent"].values())


def test_released_csv_policy_is_flagged_by_the_audit():
    rep = audit_scenario(load_scenario(N25, candidacy_seed_policy="released_csv"))
    assert not rep["ok"] and any("jennifer_moore" in i for i in rep["issues"])


@pytest.mark.skipif(not OFFICIAL.exists(), reason="official generative_agents checkout not available")
def test_reimport_reproduces_committed_scenario_files(tmp_path):
    import_official(OFFICIAL, tmp_path)
    ours = repo_path("scenarios")
    for rel in ["smallville_n25/map/the_ville.json", "smallville_n25/scenario.yaml", "pilot3/scenario.yaml", "import_audit.json"]:
        assert filecmp.cmp(tmp_path / rel, ours / rel, shallow=False), rel
    for f in (ours / "smallville_n25/agents").glob("*.yaml"):
        assert filecmp.cmp(tmp_path / "smallville_n25/agents" / f.name, f, shallow=False), f.name
