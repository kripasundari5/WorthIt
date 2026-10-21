"""Floor percentile sweep. ZERO credits.

Shows where the floor starts separating broken products from acceptable
ones. This is the evidence that the threshold is data-driven, not picked.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np

from core.db import get_session
from core.parser import _keyword_fallback as parse
from core.ranker import compute_floors, score_candidate, compute_price_scores
from core.retrieve import fetch_candidates

QUERY = "laptop under 80000 with great performance, dont mind heating"
ASPECT = "thermals"

if __name__ == "__main__":
    q = parse(QUERY)
    with get_session() as s:
        cands = fetch_candidates(s, q.constraints)

    vals = sorted(c["aspects"][ASPECT]["score"] for c in cands
                  if ASPECT in c["aspects"])
    print(f"{ASPECT} distribution ({len(vals)} products):")
    print("  " + ", ".join(f"{v:.2f}" for v in vals))

    ps = compute_price_scores(cands)

    print(f"\n{'pct':>5} {'floor':>7} {'below':>6} {'max_pen':>8}  top pick")
    print("-" * 68)
    for pct in [0, 10, 20, 30, 35, 40, 50, 60]:
        floors = compute_floors(cands, [ASPECT], percentile=pct)
        tau = floors[ASPECT]
        below = sum(1 for v in vals if v < tau)

        scored = []
        for c in cands:
            u, pen, _ = score_candidate(c, q, floors, use_floor=True,
                                        price_scores=ps)
            scored.append((u, pen, c["title"][:34]))
        scored.sort(reverse=True, key=lambda x: x[0])
        max_pen = max(p for _, p, _ in scored)

        print(f"{pct:>5} {tau:>7.3f} {below:>6} {max_pen:>8.3f}  {scored[0][2]}")