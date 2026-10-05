"""Blinded export, human imports and the exploratory judge (spec M-5, M-8)."""

from __future__ import annotations

import csv
import json

import pytest

from eval_helpers import IDS
from generative_agents.config import GAConfig
from generative_agents.evaluation.export import blinded_export, load_key
from generative_agents.evaluation.human import HUMAN_CONDITION, import_human_responses, import_rankings
from generative_agents.evaluation.judge import LABEL, judge_responses
from generative_agents.providers.mock import MockLLM

CONDS = ["full_architecture", "no_reflection", "observations_only", "no_memory_stream"]


def responses():
    out = []
    for aid in ("klaus_mueller", "maria_lopez"):
        for qid in ("self_1", "memory_4"):
            for i, c in enumerate(CONDS):
                out.append(
                    {
                        "agent_id": aid,
                        "agent_name": IDS[aid].name,
                        "question_id": qid,
                        "question": f"question {qid}",
                        "condition": c,
                        "answer": f"answer number {i} for {aid}/{qid}",
                    }
                )
    return out


def test_blinded_export_hides_conditions_and_keeps_a_separate_key(tmp_path):
    info = blinded_export(responses(), tmp_path, seed=9, identities=IDS)
    assert info["items"] == 4 and info["answers"] == 16
    sheet = (tmp_path / "rating_items.csv").read_text() + (tmp_path / "rating_form.csv").read_text()
    assert not any(c in sheet for c in CONDS)  # raters never see condition names
    for row in csv.DictReader((tmp_path / "rating_items.csv").open()):
        assert row["label"] in "ABCD"
    key = load_key(tmp_path / "blinding_key.json")
    assert sorted(key["i0001"]["labels"].values()) == sorted(CONDS)
    again = tmp_path / "again"
    blinded_export(responses(), again, seed=9, identities=IDS)
    assert load_key(again / "blinding_key.json") == key  # reproducible from the seed
    assert json.loads((tmp_path / "blinding_key.json").read_text())["do_not_share_with_raters"]
    assert (tmp_path / "rubric.md").exists() and (tmp_path / "context" / "klaus_mueller.md").exists()


def test_rankings_import_maps_letters_back_and_rejects_bad_rows(tmp_path):
    blinded_export(responses(), tmp_path, seed=9)
    key = load_key(tmp_path / "blinding_key.json")
    labels = key["i0001"]["labels"]
    good = tmp_path / "ratings.csv"
    good.write_text("rater_id,item_id,ranking\nr1,i0001,A>B>C>D\nr2,i0001,D>C>B>A\n")
    rk = import_rankings(good, key)
    assert rk[0].order == tuple(labels[x] for x in "ABCD") and rk[1].order[0] == labels["D"]
    bad = tmp_path / "bad.csv"
    bad.write_text("rater_id,item_id,ranking\nr1,i0001,A>B>C\n")
    with pytest.raises(ValueError):
        import_rankings(bad, key)
    dup = tmp_path / "dup.csv"
    dup.write_text("rater_id,item_id,ranking\nr1,i0001,A>B>C>D\nr1,i0001,B>A>C>D\n")
    with pytest.raises(ValueError):
        import_rankings(dup, key)


def test_human_responses_are_imported_never_generated(tmp_path):
    f = tmp_path / "human.csv"
    f.write_text("agent_id,question_id,answer,author_id\nklaus_mueller,self_1,Hi I'm Klaus.,w1\nmaria_lopez,self_1,Hello!,w2\n")
    rows = import_human_responses(f, question_text={"self_1": "Give an introduction of yourself."}, agent_names={a: i.name for a, i in IDS.items()})
    assert {r["condition"] for r in rows} == {HUMAN_CONDITION} and rows[0]["source"] == "human"
    assert rows[0]["provenance"]["sha256"] and rows[0]["provenance"]["one_author_per_agent"]
    bad = tmp_path / "bad.csv"
    bad.write_text("agent_id,question_id,answer,author_id\nnobody,self_1,Hi,w1\nklaus_mueller,self_1,,w1\n")
    with pytest.raises(ValueError):
        import_human_responses(bad, question_text={"self_1": "q"}, agent_names={"klaus_mueller": "Klaus Mueller"})


def test_llm_judge_is_labeled_exploratory():
    res = judge_responses(responses()[:4], IDS, GAConfig(), ledger_path=None, scope="j", provider=MockLLM(seed=1))
    assert res["label"] == LABEL == "llm_judge_exploratory"
    assert "not human" in res["note"] and all(r["label"] == LABEL for r in res["rows"])
    assert set(res["summary"]) == set(CONDS)
