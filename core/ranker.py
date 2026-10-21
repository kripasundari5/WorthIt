
"""Bounded-sacrifice ranking.

THIS FILE IS THE CONTRIBUTION. Everything else is supporting machinery.

    A user who says "I'll compromise on X" does not mean "X is irrelevant".
    They mean "X may be worse, but not broken."

Standard recommenders assign w=0 to any aspect not prioritised, making it
invisible to the ranker. A product with an unacceptable value on X can then
rank first. Here a sacrificed aspect still gets w=0 -- it never pulls a
product UP -- but falling below tau_a incurs a penalty.
"""
from __future__ import annotations

import numpy as np

from core.config import (
    FLOOR_GUARD,
    FLOOR_LAMBDA,
    FLOOR_PERCENTILE,
    MIN_MENTIONS,
    PRICE_WEIGHT,
    PRIORITY_GAMMA,
    RANKING_ASPECTS,
    USE_PRICE_EFFICIENCY,
)
from core.schemas import ParsedQuery


def compute_floors(
    candidates: list[dict],
    aspects: list[str],
    percentile: float = FLOOR_PERCENTILE,
    guard: bool = FLOOR_GUARD,
) -> dict[str, float]:
    """Derive tau_a from the candidate pool.

        Data-driven and conditional on the pool, including its price band
    and category, since hard constraints already shaped it.

    When guard=True, skip a floor if its percentile threshold is greater
    than or equal to the median of the valid scores for that aspect.
    A threshold at or above the pool median can demand that a product
    perform among the best on an aspect the user agreed could be worse.
    This safeguard is a proposed semantic rule and must be evaluated
    separately from the primary, unguarded ranking.
    """
    floors: dict[str, float] = {}

    for aspect in aspects:
        vals = [
            c["aspects"][aspect]["score"]
            for c in candidates
            if aspect in c["aspects"]
            and c["aspects"][aspect]["mentions"] >= MIN_MENTIONS
        ]

        if not vals:
            continue

        tau = float(np.percentile(vals, percentile))

        if guard and tau >= float(np.median(vals)):
            # No floor is applied to this aspect.
            # score_candidate() defaults missing floors to 0.0.
            continue

        floors[aspect] = tau

    return floors


def compute_price_scores(candidates: list[dict]) -> dict[str, float]:
    """Pool-relative price efficiency: cheapest = 1.0, dearest = 0.0.

    Objective and computed, unlike review-derived value sentiment.
    Uses a pool-relative, rank-based scale so one outlier laptop
    cannot skew the scores.
    """
    priced = [
        (c["product_id"], c["price"])
        for c in candidates
        if c.get("price") is not None
    ]

    if len(priced) < 2:
        return {pid: 0.5 for pid, _ in priced}

    prices = np.array([price for _, price in priced], dtype=float)

    if prices.max() <= prices.min():
        return {pid: 0.5 for pid, _ in priced}

    order = prices.argsort().argsort()
    scores = 1.0 - order / (len(prices) - 1)

    return {
        pid: float(score)
        for (pid, _), score in zip(priced, scores)
    }


def _priority_utility(score: float, confidence: float, gamma: float) -> float:
    """Diminishing returns, shrunk toward 0.5 by confidence."""
    adjusted = 0.5 + (score - 0.5) * confidence
    return float(adjusted ** gamma)


def score_candidate(
    cand,
    query,
    floors,
    use_floor=True,
    price_scores=None,
    use_price=USE_PRICE_EFFICIENCY,
    price_weight=PRICE_WEIGHT,
    lam=FLOOR_LAMBDA,
    gamma=PRIORITY_GAMMA,
):
    """Return (utility, floor_penalty, price_component)."""

    # Aspects excluded from ranking are ignored even if the parser tags them.
    priorities = {
        aspect: weight
        for aspect, weight in query.priorities().items()
        if aspect in RANKING_ASPECTS
    }
    total_w = sum(priorities.values()) or 1.0

    gain = 0.0

    for aspect, weight in priorities.items():
        entry = cand["aspects"].get(aspect)

        if not entry:
            continue

        gain += (weight / total_w) * _priority_utility(
            entry["score"],
            entry["confidence"],
            gamma,
        )

    penalty = 0.0

    if use_floor:
        for aspect in query.sacrifices():
            if aspect not in RANKING_ASPECTS:
                continue

            entry = cand["aspects"].get(aspect)

            if not entry or entry["mentions"] < MIN_MENTIONS:
                continue

            shortfall = max(
                0.0,
                floors.get(aspect, 0.0) - entry["score"],
            )
            penalty += lam * (shortfall ** 2)

    price_part = 0.0

    if use_price and price_scores:
        price_score = price_scores.get(cand["product_id"])

        if price_score is not None:
            # Tiebreaker: prefers cheaper laptops without allowing
            # cheap, low-quality products to dominate.
            price_part = price_weight * price_score

    return gain + price_part - penalty, penalty, price_part


def rank(
    candidates,
    query,
    use_floor=True,
    top_k=10,
    use_price=USE_PRICE_EFFICIENCY,
    price_weight=PRICE_WEIGHT,
    guard=FLOOR_GUARD,
):
    """Rank candidates. Returns (ranked, floors_used).

    use_floor=False disables floor penalties.
    use_price=False disables price-efficiency scoring.
    guard=True enables the proposed degenerate-floor safeguard.
    """
    sacrificed = [
        aspect
        for aspect in query.sacrifices()
        if aspect in RANKING_ASPECTS
    ]

    floors = (
        compute_floors(candidates, sacrificed, guard=guard)
        if sacrificed
        else {}
    )

    price_scores = compute_price_scores(candidates) if use_price else {}

    scored = []

    for candidate in candidates:
        utility, penalty, price_part = score_candidate(
            candidate,
            query,
            floors,
            use_floor,
            price_scores,
            use_price,
            price_weight,
        )

        item = dict(candidate)
        item["utility"] = utility
        item["floor_penalty"] = penalty
        item["price_component"] = price_part
        item["price_score"] = price_scores.get(
            candidate["product_id"],
            0.0,
        )

        scored.append(item)

    scored.sort(key=lambda item: item["utility"], reverse=True)

    return scored[:top_k], floors


def mmr_diversify(
    ranked: list[dict],
    lam: float = 0.7,
    top_k: int = 10,
) -> list[dict]:
    """Optional: stop the top results being one product in five colours."""
    if not ranked:
        return []

    def sim(a: dict, b: dict) -> float:
        similarity = 0.0

        if a.get("brand") and a.get("brand") == b.get("brand"):
            similarity += 0.6

        price_a, price_b = a.get("price"), b.get("price")

        if (
            price_a
            and price_b
            and abs(price_a - price_b) / max(price_a, price_b) < 0.1
        ):
            similarity += 0.4

        return similarity

    selected, pool = [ranked[0]], ranked[1:]

    while pool and len(selected) < top_k:
        best, best_val = None, -1e9

        for candidate in pool:
            value = (
                lam * candidate["utility"]
                - (1 - lam)
                * max(sim(candidate, selected_item) for selected_item in selected)
            )

            if value > best_val:
                best, best_val = candidate, value

        selected.append(best)
        pool.remove(best)

    return selected
