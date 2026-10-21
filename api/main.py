"""Minimal API for WorthIt recommendations.

Run locally with: uvicorn api.main:app --reload
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from core.config import ASPECT_LABELS, RANKING_ASPECTS
from core.db import get_session
from core.explain import explain_recommendation
from core.parser import parse_query
from core.ranker import rank
from core.retrieve import fetch_candidates
from core.schemas import (
    AspectEvidence,
    RecommendRequest,
    RecommendResponse,
    Recommendation,
)

app = FastAPI(
    title="WorthIt Recommendation API",
    description="Trade-off-aware laptop recommendations from review-derived aspect scores.",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Lightweight service health endpoint (does not verify database access)."""
    return {"status": "ok", "service": "worthit-api"}


@app.post("/recommend", response_model=RecommendResponse)
def recommend(request: RecommendRequest) -> RecommendResponse:
    """Parse a shopping query and rank matching laptops."""
    query_text = request.query.strip()
    if not query_text:
        raise HTTPException(status_code=422, detail="Query cannot be empty.")

    parsed = parse_query(query_text)
    if parsed.constraints.max_price is None:
        raise HTTPException(
            status_code=422,
            detail="Please include a maximum budget, e.g. 'laptop under 80000'.",
        )

    try:
        with get_session() as session:
            candidates = fetch_candidates(session, parsed.constraints)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable.") from exc

    if not candidates:
        return RecommendResponse(parsed=parsed, floors={}, results=[])

    ranked, floors = rank(
        candidates,
        parsed,
        use_floor=request.use_floor,
        top_k=max(1, min(request.top_k, 10)),
    )

    results = []
    for item in ranked:
        evidence = []
        for aspect in RANKING_ASPECTS:
            entry = item["aspects"].get(aspect)
            if not entry:
                continue
            evidence.append(AspectEvidence(
                aspect=aspect,
                label=ASPECT_LABELS.get(aspect, aspect),
                score=float(entry["score"]),
                confidence=float(entry["confidence"]),
                mentions=int(entry["mentions"]),
                snippet=None,
            ))

        results.append(Recommendation(
            product_id=str(item["product_id"]),
            title=str(item["title"]),
            price=item.get("price"),
            image_url=item.get("image_url"),
            utility=float(item["utility"]),
            floor_penalty=float(item["floor_penalty"]),
            aspects=evidence,
            explanation=explain_recommendation(item, parsed, floors),
        ))

    return RecommendResponse(parsed=parsed, floors=floors, results=results)
