"""Post-hoc analysis: the floor with a degeneracy guard. Read-only.

THIS IS A POST-HOC ANALYSIS. The primary result is eval/run_eval.py, run
without the guard, and that is the number to report first. This script
exists because the primary result's diagnosis identified a specific
mathematical degeneracy, not because the primary number was unwelcome.

The guard: skip the floor for any sacrificed aspect whose derived tau is
at or above the candidate pool's median for that aspect.

Justification is semantic, not empirical. A threshold at or above the
centre of the distribution is not a minimum acceptable level -- it is a
requirement to be among the best. That contradicts the user's explicit
statement that the aspect may be worse, so the constraint is ill-formed
regardless of which way it moves the metric.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv                       # noqa: E402
load_dotenv(ROOT / ".env")

import numpy as np                                   # noqa: E402

from core.config import RANKING_ASPECTS              # noqa: E402
from core.db import get_session                      # noqa: E402
from core.parser import _keyword_fallback as parse   # noqa: E402
from core.ranker import rank                         # noqa: E402
from core.retrieve import fetch_candidates           # noqa: E402
from eval.run_eval import (average_precision, ndcg_at_k,   # noqa: E402
                           paired_bootstrap)

QUERIES = ROOT / "eval" / "queries.json"
K = 10


def main():
    queries = json.loads(QUERIES.read_text())
    names = ["weight_zero", "floor_raw", "floor_guarded",
             "full_raw", "full_guarded"]
    nd = {s: [] for s in names}
    ap = {s: [] for s in names}
    n_used = 0

    with get_session() as session:
        for q in queries:
            rel = {k: v for k, v in (q.get("relevance") or {}).items()
                   if k != "__none__"}
            if not rel:
                continue
            parsed = parse(q["query"])
            cands = fetch_candidates(session, parsed.constraints)
            if not cands or not [a for a in parsed.sacrifices()
                                 if a in RANKING_ASPECTS]:
                continue

            runs = {
                "weight_zero": rank(cands, parsed, use_floor=False,
                                    use_price=False, top_k=K)[0],
                "floor_raw": rank(cands, parsed, use_floor=True,
                                  use_price=False, top_k=K, guard=False)[0],
                "floor_guarded": rank(cands, parsed, use_floor=True,
                                      use_price=False, top_k=K,
                                      guard=True)[0],
                "full_raw": rank(cands, parsed, use_floor=True,
                                 use_price=True, top_k=K, guard=False)[0],
                "full_guarded": rank(cands, parsed, use_floor=True,
                                     use_price=True, top_k=K, guard=True)[0],
            }
            for s, run in runs.items():
                ids = [c["product_id"] for c in run]
                nd[s].append(ndcg_at_k(ids, rel, K))
                ap[s].append(average_precision(ids, rel, K))
            n_used += 1

    if not n_used:
        print("No evaluable queries.")
        return

    print("POST-HOC ANALYSIS -- degeneracy-guarded floor")
    print("Primary result is eval/run_eval.py (unguarded). Report that first.")
    print(f"\n{n_used} queries, k={K}\n")

    print(f"{'system':<16}{'nDCG@10':>10}{'MAP@10':>10}")
    print("-" * 36)
    for s in names:
        print(f"{s:<16}{np.mean(nd[s]):>10.4f}{np.mean(ap[s]):>10.4f}")

    print("\nPAIRED COMPARISONS  (paired bootstrap, 10k resamples)")
    print("-" * 66)
    for base, test, label in [
        ("weight_zero", "floor_raw", "floor, unguarded (primary)"),
        ("weight_zero", "floor_guarded", "floor, guarded (post-hoc)"),
        ("floor_raw", "floor_guarded", "guard contribution"),
        ("weight_zero", "full_guarded", "full system, guarded"),
    ]:
        delta, p = paired_bootstrap(nd[base], nd[test])
        sig = "*" if p < 0.05 else " "
        print(f"  {label:<28}{delta:+.4f}  p={p:.4f} {sig}")

    changed = sum(1 for a, b in zip(nd["floor_raw"], nd["floor_guarded"])
                  if abs(a - b) > 1e-9)
    print(f"\nGuard altered {changed}/{n_used} queries.")
    print("A guarded floor that is never ill-formed can only decline to "
          "apply;\nit never adds a constraint the unguarded version lacked.")


if __name__ == "__main__":
    main()