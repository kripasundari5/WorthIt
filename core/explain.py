"""Short, transparent explanations for ranked recommendations."""
from core.config import ASPECT_LABELS, RANKING_ASPECTS


def explain_recommendation(candidate: dict, query, floors: dict[str, float]) -> str:
    """Explain the product using its priority scores and any floor penalty."""
    priorities = [a for a in query.priorities() if a in RANKING_ASPECTS]
    sacrifices = [a for a in query.sacrifices() if a in RANKING_ASPECTS]
    parts = []

    if priorities:
        best = []
        for aspect in priorities:
            entry = candidate.get("aspects", {}).get(aspect)
            if entry:
                best.append(
                    f"{ASPECT_LABELS.get(aspect, aspect)} score {entry['score']:.2f}"
                )
        if best:
            parts.append("Matches your priority: " + ", ".join(best) + ".")

    if candidate.get("floor_penalty", 0) > 0:
        below = []
        for aspect in sacrifices:
            entry = candidate.get("aspects", {}).get(aspect)
            tau = floors.get(aspect)
            if entry and tau is not None and entry["score"] < tau:
                below.append(
                    f"{ASPECT_LABELS.get(aspect, aspect)} {entry['score']:.2f} is below its floor {tau:.2f}"
                )
        if below:
            parts.append("Trade-off penalty: " + "; ".join(below) + ".")
    elif sacrifices:
        parts.append("No bounded-sacrifice penalty was applied to this product.")

    if candidate.get("price") is not None:
        parts.append(f"Listed price: ₹{candidate['price']:,.0f}.")

    return " ".join(parts) or "Ranked using the available review-derived aspect scores and query settings."
