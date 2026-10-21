"""Break the floor's effect down by sacrificed aspect. Read-only.

Tests one hypothesis: the pool-relative percentile floor degenerates when
the sacrificed aspect's score distribution is saturated near its maximum.
If tau lands at or above the pool median, it is not a floor -- it is a
requirement for the best, which contradicts the user's stated willingness
to accept worse.
"""
import json
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv                       # noqa: E402
load_dotenv(ROOT / ".env")

import numpy as np                                   # noqa: E402

from core.config import MIN_MENTIONS, RANKING_ASPECTS   # noqa: E402
from core.db import get_session                      # noqa: E402
from core.parser import _keyword_fallback as parse   # noqa: E402
from core.ranker import compute_floors, rank         # noqa: E402
from core.retrieve import fetch_candidates           # noqa: E402
from eval.run_eval import ndcg_at_k                  # noqa: E402

QUERIES = ROOT / "eval" / "queries.json"


def main():
    queries = json.loads(QUERIES.read_text())
    by_aspect = defaultdict(list)
    rows = []

    with get_session() as session:
        for q in queries:
            rel = {k: v for k, v in (q.get("relevance") or {}).items()
                   if k != "__none__"}
            if not rel:
                continue
            parsed = parse(q["query"])
            cands = fetch_candidates(session, parsed.constraints)
            sac = [a for a in parsed.sacrifices() if a in RANKING_ASPECTS]
            if not cands or not sac:
                continue

            wz = [c["product_id"] for c in
                  rank(cands, parsed, use_floor=False, use_price=False,
                       top_k=10)[0]]
            fl = [c["product_id"] for c in
                  rank(cands, parsed, use_floor=True, use_price=False,
                       top_k=10)[0]]
            delta = ndcg_at_k(fl, rel, 10) - ndcg_at_k(wz, rel, 10)

            floors = compute_floors(cands, sac)
            for a in sac:
                vals = [c["aspects"][a]["score"] for c in cands
                        if a in c["aspects"]
                        and c["aspects"][a]["mentions"] >= MIN_MENTIONS]
                if not vals:
                    continue
                tau = floors.get(a, 0.0)
                med = float(np.median(vals))
                mx = float(max(vals))
                below = sum(1 for v in vals if v < tau)
                by_aspect[a].append(delta)
                rows.append({
                    "q": q["id"], "aspect": a, "tau": tau, "med": med,
                    "max": mx, "n": len(vals), "below": below,
                    "frac": below / len(vals), "delta": delta,
                })

    print("=" * 74)
    print("FLOOR EFFECT BY SACRIFICED ASPECT")
    print("=" * 74)
    print(f"{'aspect':<16}{'queries':>8}{'mean dNDCG':>13}"
          f"{'mean tau':>10}{'mean med':>10}{'% pool below':>14}")
    print("-" * 74)

    order = sorted(by_aspect, key=lambda a: np.mean(by_aspect[a]))
    for a in order:
        sub = [r for r in rows if r["aspect"] == a]
        print(f"{a:<16}{len(sub):>8}{np.mean(by_aspect[a]):>+13.4f}"
              f"{np.mean([r['tau'] for r in sub]):>10.2f}"
              f"{np.mean([r['med'] for r in sub]):>10.2f}"
              f"{100*np.mean([r['frac'] for r in sub]):>13.0f}%")

    print("\n" + "=" * 74)
    print("DEGENERACY CHECK   tau >= pool median means tau is not a floor")
    print("=" * 74)
    bad = [r for r in rows if r["tau"] >= r["med"]]
    good = [r for r in rows if r["tau"] < r["med"]]
    print(f"  degenerate (tau >= median) : {len(bad):>3} query-aspects")
    print(f"  valid      (tau <  median) : {len(good):>3} query-aspects")

    if bad:
        print(f"\n  mean dNDCG when degenerate : "
              f"{np.mean([r['delta'] for r in bad]):+.4f}")
    if good:
        print(f"  mean dNDCG when valid      : "
              f"{np.mean([r['delta'] for r in good]):+.4f}")

    if bad:
        print("\n  Degenerate cases:")
        print(f"    {'query':<7}{'aspect':<16}{'tau':>6}{'median':>8}"
              f"{'max':>6}{'dNDCG':>9}")
        for r in sorted(bad, key=lambda x: x["delta"])[:10]:
            print(f"    {r['q']:<7}{r['aspect']:<16}{r['tau']:>6.2f}"
                  f"{r['med']:>8.2f}{r['max']:>6.2f}{r['delta']:>+9.3f}")

    if bad:
        # Percentages mislead when the total is near zero; show sums.
        print(f"\n  summed dNDCG, degenerate : "
              f"{sum(r['delta'] for r in bad):+.4f}")
        print(f"  summed dNDCG, valid      : "
              f"{sum(r['delta'] for r in good):+.4f}")


if __name__ == "__main__":
    main()