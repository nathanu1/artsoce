"""Appendix B banks and placeholder selection (spec M-3)."""

from __future__ import annotations

from collections import Counter

import pytest

from eval_helpers import IDS, toy_run
from generative_agents.evaluation.question_bank import CATEGORIES, QuestionBank, select_placeholders

REF = "configs/questions/appendix_b_reference.yaml"
ADAPTED = "configs/questions/appendix_b_adapted.yaml"


def test_reference_bank_has_the_25_questions_with_the_papers_wording():
    bank = QuestionBank.load(REF)
    assert len(bank.questions) == 25
    assert Counter(q.category for q in bank.questions) == dict.fromkeys(CATEGORIES, 5)
    assert bank.by_id("self_1").text == "Give an introduction of yourself."
    assert bank.by_id("reactions_1").text == "Your breakfast is burning! What would you do?"
    assert bank.by_id("reflections_2").text.endswith("what book do you think she will like and why?")
    assert bank.by_id("memory_1").paper_text == "Who is [Wolfgang Schulz]?"
    adapted = QuestionBank.load(ADAPTED)
    assert [q.id for q in adapted.questions] == [q.id for q in bank.questions]
    assert " she " not in adapted.by_id("reflections_2").text and "her" not in adapted.by_id("reflections_4").text


def test_placeholders_follow_the_appendix_and_are_recorded():
    _, db, _, _ = toy_run()
    names = {a: i.name for a, i in IDS.items()}
    sel = select_placeholders(db, "klaus_mueller", names, ["You know Maria Lopez from the dorm"], seed=4)
    assert sel.bindings["frequent_1"] == "Isabella Rodriguez"  # the only conversation partner
    assert sel.record["frequent"]["tied"] == ["Isabella Rodriguez"]
    assert set([sel.bindings["interacted_1"], sel.bindings["interacted_2"]]) == {"Isabella Rodriguez", "Maria Lopez"}
    assert "seed_mentions" in sel.record["interacted"]["source"]  # one partner, so a seed-named agent fills in
    again = select_placeholders(db, "klaus_mueller", names, ["You know Maria Lopez from the dorm"], seed=4)
    assert again.bindings == sel.bindings  # recorded seed makes it reproducible
    assert sel.bindings["nonexistent_person"] == "Kane Martinez"
    q = QuestionBank.load(REF).by_id("reflections_3")
    assert q.render(sel.bindings) == "If you had to get something Isabella Rodriguez likes for her birthday, what would you get her?"


def test_nonexistent_person_must_not_exist():
    _, db, _, _ = toy_run()
    names = {"x": "Kane Martinez", "maria_lopez": "Maria Lopez"}
    with pytest.raises(ValueError):
        select_placeholders(db, "maria_lopez", names, [], seed=0)
