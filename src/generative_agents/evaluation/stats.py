"""Rank analysis for the controlled evaluation (paper §6.4 p. 14; spec M-6, M-7).

The authors' pipeline: TrueSkill ratings from the rankings, a Kruskal–Wallis test on the raw
ranks, Dunn post-hoc pairwise tests, Holm–Bonferroni adjustment.

Our addition, labeled as such: the study is within-subjects, so a Friedman test over complete
rankings (one block per rater × item) with paired Wilcoxon signed-rank follow-ups and Holm
adjustment is offered too. It is not the authors' method.

Nothing here runs without genuine rating data; ``analyze`` refuses an empty or invalid input.
TrueSkill's sigma is the rating's uncertainty, not a subject-level standard deviation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from typing import Any

import numpy as np
from scipy import stats as sps


@dataclass(frozen=True)
class Ranking:
    rater_id: str
    item_id: str
    order: tuple[str, ...]  # conditions, most believable first
    agent_id: str | None = None
    question_id: str | None = None


def validate_rankings(rankings: list[Ranking]) -> list[str]:
    errs = []
    for r in rankings:
        if len(r.order) < 2:
            errs.append(f"{r.rater_id}/{r.item_id}: a ranking needs at least two conditions")
        if len(set(r.order)) != len(r.order):
            errs.append(f"{r.rater_id}/{r.item_id}: a condition appears twice")
    return errs


def holm(pvalues: list[float]) -> list[float]:
    """Holm–Bonferroni step-down adjustment (monotone, capped at 1)."""

    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def trueskill_ratings(rankings: list[Ranking], conditions: list[str]) -> dict[str, dict[str, float]]:
    import trueskill

    env = trueskill.TrueSkill(draw_probability=0.0)
    ratings = {c: env.create_rating() for c in conditions}
    for r in sorted(rankings, key=lambda x: (x.rater_id, x.item_id)):
        order = [c for c in r.order if c in ratings]
        if len(order) < 2:
            continue
        new = env.rate([(ratings[c],) for c in order], ranks=list(range(len(order))))
        for c, (rt,) in zip(order, new, strict=True):
            ratings[c] = rt
    return {c: {"mu": round(float(v.mu), 3), "sigma": round(float(v.sigma), 3)} for c, v in ratings.items()}


def cohens_d(a: dict[str, float], b: dict[str, float]) -> float:
    """Effect size between two TrueSkill ratings, treating each as N(mu, sigma²)."""

    pooled = math.sqrt((a["sigma"] ** 2 + b["sigma"] ** 2) / 2)
    return (a["mu"] - b["mu"]) / pooled if pooled else float("nan")


def rank_positions(rankings: list[Ranking], conditions: list[str]) -> dict[str, list[int]]:
    pos: dict[str, list[int]] = {c: [] for c in conditions}
    for r in rankings:
        for i, c in enumerate(r.order, start=1):
            if c in pos:
                pos[c].append(i)
    return pos


def kruskal_dunn(rankings: list[Ranking], conditions: list[str]) -> dict[str, Any]:
    groups = rank_positions(rankings, conditions)
    if any(len(v) < 2 for v in groups.values()):
        return {"computed": False, "reason": "each condition needs at least two ranks"}
    h, p = sps.kruskal(*[groups[c] for c in conditions])
    values = np.concatenate([np.asarray(groups[c], dtype=float) for c in conditions])
    labels = [c for c in conditions for _ in groups[c]]
    ranks = sps.rankdata(values)
    n = len(values)
    _, counts = np.unique(values, return_counts=True)
    ties = float(np.sum(counts**3 - counts))
    mean_rank = {c: float(np.mean([ranks[i] for i, lab in enumerate(labels) if lab == c])) for c in conditions}
    pairs = []
    for a, b in combinations(conditions, 2):
        se = math.sqrt((n * (n + 1) / 12 - ties / (12 * (n - 1))) * (1 / len(groups[a]) + 1 / len(groups[b])))
        z = (mean_rank[a] - mean_rank[b]) / se if se else 0.0
        pairs.append({"a": a, "b": b, "z": round(z, 4), "p": 2 * (1 - sps.norm.cdf(abs(z)))})
    adj = holm([x["p"] for x in pairs])
    for x, q in zip(pairs, adj, strict=True):
        x["p_holm"] = q
    return {
        "computed": True,
        "method": "authors (paper §6.4): Kruskal–Wallis on raw ranks; Dunn post-hoc; Holm–Bonferroni",
        "H": float(h),
        "df": len(conditions) - 1,
        "p": float(p),
        "mean_rank_position": {c: float(np.mean(groups[c])) for c in conditions},
        "dunn": pairs,
    }


def friedman_wilcoxon(rankings: list[Ranking], conditions: list[str]) -> dict[str, Any]:
    blocks = [r for r in rankings if set(r.order) == set(conditions)]
    if len(blocks) < 2 or len(conditions) < 3:
        return {"computed": False, "reason": "needs at least two complete rankings over at least three conditions"}
    m = np.array([[r.order.index(c) + 1 for c in conditions] for r in blocks], dtype=float)
    chi2, p = sps.friedmanchisquare(*[m[:, j] for j in range(len(conditions))])
    pairs = []
    for i, j in combinations(range(len(conditions)), 2):
        d = m[:, i] - m[:, j]
        if np.all(d == 0):
            pairs.append({"a": conditions[i], "b": conditions[j], "statistic": 0.0, "p": 1.0})
            continue
        res = sps.wilcoxon(m[:, i], m[:, j])
        pairs.append({"a": conditions[i], "b": conditions[j], "statistic": float(res.statistic), "p": float(res.pvalue)})
    adj = holm([x["p"] for x in pairs])
    for x, q in zip(pairs, adj, strict=True):
        x["p_holm"] = q
    return {
        "computed": True,
        "method": "OURS, not the authors': Friedman over complete rankings (blocks = rater × item), paired Wilcoxon signed-rank, Holm",
        "blocks": len(blocks),
        "chi2": float(chi2),
        "df": len(conditions) - 1,
        "p": float(p),
        "wilcoxon": pairs,
    }


def analyze(rankings: list[Ranking], conditions: list[str], *, source: str) -> dict[str, Any]:
    if not rankings:
        return {"computed": False, "reason": "no rating data; nothing is computed without genuine ratings"}
    errs = validate_rankings(rankings)
    if errs:
        raise ValueError("invalid rankings: " + "; ".join(errs[:10]))
    ts = trueskill_ratings(rankings, conditions)
    best = max(ts, key=lambda c: ts[c]["mu"])
    worst = min(ts, key=lambda c: ts[c]["mu"])
    return {
        "computed": True,
        "source": source,
        "raters": len({r.rater_id for r in rankings}),
        "rankings": len(rankings),
        "conditions": conditions,
        "trueskill": ts,
        "trueskill_note": "sigma is TrueSkill's rating uncertainty, not a subject-level standard deviation",
        "cohens_d_best_vs_worst": {"a": best, "b": worst, "d": round(cohens_d(ts[best], ts[worst]), 3)},
        "kruskal_dunn": kruskal_dunn(rankings, conditions),
        "friedman_wilcoxon_ours": friedman_wilcoxon(rankings, conditions),
    }
