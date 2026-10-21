"""Aggregate aspect mentions into the product x aspect matrix.

score      = weighted mean sentiment, mapped to 0..1
             weights = helpfulness x time_decay
confidence = saturating function of mention count
"""
from __future__ import annotations

import math
from datetime import datetime

from sqlalchemy import select

from core.config import TIME_DECAY_HALFLIFE_DAYS
from core.db import AspectMention, AspectScore, Review


def time_decay(created: datetime | None,
               half_life_days: float = TIME_DECAY_HALFLIFE_DAYS) -> float:
    """Recent reviews weigh more. Firmware updates change reality."""
    if created is None:
        return 0.5
    age_days = max(0.0, (datetime.utcnow() - created).days)
    return 0.5 ** (age_days / half_life_days)


def helpfulness_weight(votes: int) -> float:
    """Diminishing: 0 votes -> 1.0, 10 -> ~2.4, 100 -> ~3.6."""
    return 1.0 + math.log1p(max(0, votes))


def confidence(mentions: int, k: float = 8.0) -> float:
    """Saturating. 3 -> 0.27, 8 -> 0.50, 20 -> 0.71."""
    return mentions / (mentions + k)


def aggregate_product(session, product_id: str) -> list[AspectScore]:
    """Recompute all aspect scores for one product."""
    rows = session.execute(
        select(AspectMention, Review)
        .join(Review, Review.id == AspectMention.review_id)
        .where(AspectMention.product_id == product_id)
    ).all()

    buckets: dict[str, list[tuple[float, float]]] = {}
    for mention, review in rows:
        w = helpfulness_weight(review.helpful_votes) * time_decay(review.created_at)
        if review.verified:
            w *= 1.2
        buckets.setdefault(mention.aspect, []).append((mention.sentiment, w))

    out = []
    for aspect, pairs in buckets.items():
        total_w = sum(w for _, w in pairs)
        if total_w == 0:
            continue
        mean_sent = sum(s * w for s, w in pairs) / total_w
        score = (mean_sent + 1.0) / 2.0          # -1..1  ->  0..1
        n = len(pairs)

        existing = session.execute(
            select(AspectScore).where(
                AspectScore.product_id == product_id,
                AspectScore.aspect == aspect)
        ).scalar_one_or_none()

        if existing:
            existing.score = score
            existing.confidence = confidence(n)
            existing.mentions = n
            existing.updated_at = datetime.utcnow()
            out.append(existing)
        else:
            rec = AspectScore(product_id=product_id, aspect=aspect,
                              score=score, confidence=confidence(n),
                              mentions=n)
            session.add(rec)
            out.append(rec)

    session.commit()
    return out