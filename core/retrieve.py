"""Candidate retrieval: hard constraints -> candidate dicts for the ranker."""
from __future__ import annotations

from sqlalchemy import select

from core.db import AspectScore, Product


def fetch_candidates(session, constraints, limit: int = 500) -> list[dict]:
    stmt = select(Product)
    if constraints.max_price is not None:
        stmt = stmt.where(Product.price <= constraints.max_price)
    if constraints.min_price is not None:
        stmt = stmt.where(Product.price >= constraints.min_price)
    if constraints.brands_include:
        stmt = stmt.where(Product.brand.in_(constraints.brands_include))
    if constraints.brands_exclude:
        stmt = stmt.where(Product.brand.notin_(constraints.brands_exclude))
    stmt = stmt.limit(limit)

    products = session.execute(stmt).scalars().all()
    if not products:
        return []

    ids = [p.id for p in products]
    scores = session.execute(
        select(AspectScore).where(AspectScore.product_id.in_(ids))
    ).scalars().all()

    by_product: dict[str, dict] = {}
    for s in scores:
        by_product.setdefault(s.product_id, {})[s.aspect] = {
            "score": s.score,
            "confidence": s.confidence,
            "mentions": s.mentions,
        }

    return [
        {
            "product_id": p.id,
            "title": p.title,
            "brand": p.brand,
            "price": p.price,
            "image_url": p.image_url,
            "avg_rating": p.avg_rating,
            "aspects": by_product.get(p.id, {}),
        }
        for p in products
        # Needs aspect data to score, and a price for the efficiency term.
        if by_product.get(p.id) and p.price is not None
    ]