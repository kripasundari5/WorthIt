"""Score the labelled query set. ZERO credits, no API calls.

Reports nDCG@10 and MAP@10 for four systems over the same candidate pools,
then runs a paired bootstrap on the comparison that isolates the floor.

Systems
  rating_sort   budget filter, sort by platform rating        (deployed norm)
  weight_zero   priority aspects only                         (standard KBRS)
  floor_only    weight_zero + bounded sacrifice               (isolates floor)
  full          floor_only + price efficiency                 (proposed)

The pairing that matters is weight_zero -> floor_only: identical in every
component except the floor term, so any difference is attributable to it.

Products outside a query's judged pool are treated as relevance 0, the
standard assumption for pooled evaluation.
"""
import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv                       # noqa: E402
load_dotenv(ROOT / ".env")

import numpy as np                                   # noqa: E402

from core.db import get_session                      # noqa: E402
from core.parser import _keyword_fallback as parse   # noqa: E402
from core.ranker import rank                         # noqa: E402
from core.retrieve import fetch_candidates           # noqa: E402

QUERIES = ROOT / "eval" / "queries.json"
K = 10


# ---------------------------------------------------------------- metrics
def dcg(gains):
    return sum(g / np.log2(i + 2) for i, g in enumerate(gains))


def ndcg_at_k(ranked_ids, relevance, k=K):
    """Graded nDCG. Ideal ranking is the judged set sorted descending."""
    gains = [relevance.get(pid, 0) for pid in ranked_ids[:k]]
    ideal = sorted(relevance.values(), reverse=True)[:k]
    denom = dcg(ideal)
    return dcg(gains) / denom if denom > 0 else 0.0


def average_precision(ranked_ids, relevance, k=K):
    """Binary AP, relevant = label >= 2 (good or excellent)."""
    hits, total = 0, 0.0
    for i, pid in enumerate(ranked_ids[:k], 1):
        if relevance.get(pid, 0) >= 2:
            hits += 1
            total += hits / i
    n_rel = sum(1 for v in relevance.values() if v >= 2)
    return total / min(n_rel, k) if n_rel else 0.0


# ---------------------------------------------------------------- systems
def run_systems(cands, parsed):
    """Return {system_name: [product_id, ...]} over one candidate pool."""
    return {
        "rating_sort": [
            c["product_id"] for c in
            sorted(cands, key=lambda x: x.get("avg_rating") or 0,
                   reverse=True)[:K]
        ],
        "weight_zero": [
            c["product_id"] for c in
            rank(cands, parsed, use_floor=False, use_price=False, top_k=K)[0]
        ],
        "floor_only": [
            c["product_id"] for c in
            rank(cands, parsed, use_floor=True, use_price=False, top_k=K)[0]
        ],
        "full": [
            c["product_id"] for c in
            rank(cands, parsed, use_floor=True, use_price=True, top_k=K)[0]
        ],
    }


SYSTEMS = ["rating_sort", "weight_zero", "floor_only", "full"]


def evaluate(queries, verbose=False):
    nd = {s: [] for s in SYSTEMS}
    ap = {s: [] for s in SYSTEMS}
    used, skipped = [], []

    with get_session() as session:
        for q in queries:
            rel = {k: v for k, v in (q.get("relevance") or {}).items()
                   if k != "__none__"}
            if not rel:
                skipped.append((q["id"], "no judgements"))
                continue

            parsed = parse(q["query"])
            cands = fetch_candidates(session, parsed.constraints)
            if not cands:
                skipped.append((q["id"], "no candidates"))
                continue
            if not parsed.sacrifices():
                skipped.append((q["id"], "parser found no sacrifice"))
                continue

            runs = run_systems(cands, parsed)
            for s, ids in runs.items():
                nd[s].append(ndcg_at_k(ids, rel))
                ap[s].append(average_precision(ids, rel))
            used.append(q["id"])

            if verbose:
                d = nd["floor_only"][-1] - nd["weight_zero"][-1]
                flag = (f"  <-- floor {d:+.3f}" if abs(d) > 1e-9 else "")
                print(f"  {q['id']}  wz={nd['weight_zero'][-1]:.3f} "
                      f"fl={nd['floor_only'][-1]:.3f} "
                      f"full={nd['full'][-1]:.3f}{flag}")

    return nd, ap, used, skipped


# ------------------------------------------------------------ significance
def paired_bootstrap(base, test, n=10000, seed=0):
    """One-sided p for 'test > base' on paired per-query scores."""
    rng = np.random.default_rng(seed)
    diffs = np.array(test) - np.array(base)
    observed = diffs.mean()
    if len(diffs) == 0:
        return 0.0, 1.0
    idx = rng.integers(0, len(diffs), size=(n, len(diffs)))
    means = diffs[idx].mean(axis=1)
    # Null: no improvement. p = fraction of resamples at or below zero.
    return float(observed), float((means <= 0).mean())


def main(verbose=False):
    queries = json.loads(QUERIES.read_text())
    nd, ap, used, skipped = evaluate(queries, verbose)

    if not used:
        print("No evaluable queries. Check that queries.json has labels.")
        return

    print(f"\nEvaluated {len(used)} of {len(queries)} queries  (k={K})")
    if skipped:
        print(f"Skipped {len(skipped)}:")
        for qid, why in skipped:
            print(f"   {qid}  {why}")

    print(f"\n{'system':<14}{'nDCG@10':>10}{'MAP@10':>10}")
    print("-" * 34)
    for s in SYSTEMS:
        print(f"{s:<14}{np.mean(nd[s]):>10.4f}{np.mean(ap[s]):>10.4f}")

    print("\nPAIRED COMPARISONS  (paired bootstrap, 10k resamples)")
    print("-" * 60)
    pairs = [
        ("weight_zero", "floor_only", "floor contribution"),
        ("floor_only", "full", "price contribution"),
        ("weight_zero", "full", "both components"),
        ("rating_sort", "full", "vs deployed baseline"),
    ]
    for base, test, label in pairs:
        delta, p = paired_bootstrap(nd[base], nd[test])
        sig = "*" if p < 0.05 else " "
        print(f"  {label:<24} {base:>12} -> {test:<12} "
              f"{delta:+.4f}  p={p:.4f} {sig}")

    changed = sum(1 for a, b in zip(nd["weight_zero"], nd["floor_only"])
                  if abs(a - b) > 1e-9)
    print(f"\nFloor altered the ranking in {changed}/{len(used)} queries.")
    if changed == 0:
        print("  No query had a candidate below its derived floor -- check "
              "MIN_MENTIONS and FLOOR_PERCENTILE before reporting this.")


if __name__ == "__main__":
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("-v", "--verbose", action="store_true",
                     help="per-query nDCG")
    main(verbose=ap_.parse_args().verbose)