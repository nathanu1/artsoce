"""Rank statistics (spec M-6, M-7)."""

from __future__ import annotations

import pytest
from scipy import stats as sps

from generative_agents.evaluation.stats import Ranking, analyze, holm, kruskal_dunn, rank_positions, trueskill_ratings

C = ["full", "no_reflection", "no_memory"]


def consistent(n=20):
    return [Ranking(f"r{i}", "i1", tuple(C)) for i in range(n)]


def test_holm_step_down():
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm([0.5, 0.9]) == pytest.approx([1.0, 1.0])  # monotone step-down


def test_trueskill_orders_conditions_by_their_rankings():
    ts = trueskill_ratings(consistent(), C)
    assert ts["full"]["mu"] > ts["no_reflection"]["mu"] > ts["no_memory"]["mu"]
    assert all(v["sigma"] > 0 for v in ts.values())


def test_kruskal_matches_scipy_and_dunn_separates_extremes():
    rk = consistent(10) + [Ranking(f"s{i}", "i1", ("no_reflection", "full", "no_memory")) for i in range(5)]
    res = kruskal_dunn(rk, C)
    groups = rank_positions(rk, C)
    h, p = sps.kruskal(*[groups[c] for c in C])
    assert res["H"] == pytest.approx(h) and res["p"] == pytest.approx(p)
    pair = next(x for x in res["dunn"] if {x["a"], x["b"]} == {"full", "no_memory"})
    assert pair["p_holm"] < 0.05 and pair["p_holm"] >= pair["p"]
    same = kruskal_dunn([Ranking(f"r{i}", "i", tuple(C) if i % 2 else tuple(reversed(C))) for i in range(10)], ["full", "no_memory"])
    assert same["dunn"][0]["z"] == pytest.approx(0.0)


def test_analysis_needs_genuine_data_and_labels_our_addition():
    assert analyze([], C, source="human")["computed"] is False
    res = analyze(consistent(), C, source="human")
    assert res["friedman_wilcoxon_ours"]["method"].startswith("OURS")
    assert "authors" in res["kruskal_dunn"]["method"]
    assert res["cohens_d_best_vs_worst"]["a"] == "full"
    with pytest.raises(ValueError):
        analyze([Ranking("r", "i", ("full", "full"))], C, source="human")
