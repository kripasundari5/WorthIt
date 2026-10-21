"""Diagnose why the floor reduced nDCG. ZERO credits, read-only.

Does NOT change labels. Reports three things:

  A. Rubric agreement -- do the recorded labels follow the written rubric?
     If they do not, the benchmark is not testing the floor hypothesis.

  B. Metric saturation -- nDCG at 3, 5 and 10. With pools of 6-15 products,
     nDCG@10 ranks nearly the whole pool and has little headroom.

  C. Worst cases -- the queries where the floor hurt most, with the
     products it demoted and the labels you gave them.
"""
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
from core.ranker import compute_floors, rank         # noqa: E402
from core.retrieve import fetch_candidates           # noqa: E402
from eval.run_eval import ndcg_at_k                  # noqa: E402

QUERIES = ROOT / "eval" / "queries.json"


def rubric_label(cand, priority, sacrifice):
    """What the written rubric prescribes. For comparison only."""
    if not priority:
        return None
    e = cand["aspects"].get(priority[0])
    if not e:
        return 0
    if e["score"] >= 0.80:
        lab = 3
    elif e["score"] >= 0.60:
        lab = 2
    elif e["score"] >= 0.40:
        lab = 1
    else:
        return 0

    if e["mentions"] < 2:              # step 4: evidence cap
        lab = min(lab, 2)

    for a in sacrifice:                # step 2: bounded sacrifice
        es = cand["aspects"].get(a)
        if not es:
            continue
        if es["score"] < 0.15:
            lab = min(lab, 1)
        elif es["score"] < 0.35:
            lab = max(0, lab - 1)
    return lab


def main():
    queries = json.loads(QUERIES.read_text())

    agree = disagree = 0
    higher = lower = 0
    sac_violations = []          # labelled high despite broken sacrifice
    per_query = []

    with get_session() as session:
        for q in queries:
            rel = {k: v for k, v in (q.get("relevance") or {}).items()
                   if k != "__none__"}
            if not rel:
                continue
            parsed = parse(q["query"])
            cands = fetch_candidates(session, parsed.constraints)
            if not cands or not parsed.sacrifices():
                continue

            by_id = {c["product_id"]: c for c in cands}
            priority = list(parsed.priorities())
            sacrifice = parsed.sacrifices()

            for pid, given in rel.items():
                c = by_id.get(pid)
                if not c:
                    continue
                want = rubric_label(c, priority, sacrifice)
                if want is None:
                    continue
                if want == given:
                    agree += 1
                else:
                    disagree += 1
                    if given > want:
                        higher += 1
                    else:
                        lower += 1

                for a in sacrifice:
                    es = c["aspects"].get(a)
                    if es and es["score"] < 0.15 and given >= 2:
                        sac_violations.append(
                            (q["id"], c["title"][:34], a, es["score"], given))

            wz = [x["product_id"] for x in
                  rank(cands, parsed, use_floor=False, use_price=False,
                       top_k=10)[0]]
            fl = [x["product_id"] for x in
                  rank(cands, parsed, use_floor=True, use_price=False,
                       top_k=10)[0]]
            per_query.append({
                "id": q["id"], "rel": rel, "cands": by_id,
                "priority": priority, "sacrifice": sacrifice,
                "wz": wz, "fl": fl, "pool": len(rel),
                "d10": ndcg_at_k(fl, rel, 10) - ndcg_at_k(wz, rel, 10),
                "d5": ndcg_at_k(fl, rel, 5) - ndcg_at_k(wz, rel, 5),
                "d3": ndcg_at_k(fl, rel, 3) - ndcg_at_k(wz, rel, 3),
                "wz10": ndcg_at_k(wz, rel, 10),
                "wz5": ndcg_at_k(wz, rel, 5),
                "wz3": ndcg_at_k(wz, rel, 3),
            })

    # ------------------------------------------------- A. rubric agreement
    total = agree + disagree
    print("=" * 66)
    print("A. RUBRIC AGREEMENT")
    print("=" * 66)
    if total:
        print(f"  judgements compared : {total}")
        print(f"  match rubric        : {agree}  ({100*agree/total:.0f}%)")
        print(f"  differ              : {disagree}  "
              f"({100*disagree/total:.0f}%)")
        print(f"    labelled HIGHER than rubric : {higher}")
        print(f"    labelled LOWER  than rubric : {lower}")

    print(f"\n  Step-2 violations (sacrificed aspect < 0.15 but labelled "
          f">= 2): {len(sac_violations)}")
    for qid, title, a, sc, lab in sac_violations[:12]:
        print(f"    {qid}  {title:<34} {a} {sc:.2f} -> labelled {lab}")
    if len(sac_violations) > 12:
        print(f"    ... and {len(sac_violations) - 12} more")

    if total and higher > lower * 2 and len(sac_violations) > 10:
        print("\n  READING: labels are systematically more generous than the"
              "\n  rubric on products with a broken sacrificed aspect. The"
              "\n  floor demotes exactly those, so it MUST lose nDCG here."
              "\n  The benchmark is not testing the stated hypothesis.")

    # ------------------------------------------------ B. metric saturation
    print("\n" + "=" * 66)
    print("B. METRIC SATURATION")
    print("=" * 66)
    pools = [p["pool"] for p in per_query]
    print(f"  judged pool size: min={min(pools)} "
          f"median={int(np.median(pools))} max={max(pools)}")
    print(f"\n  {'cutoff':<8}{'weight_zero':>13}{'floor delta':>14}")
    print("  " + "-" * 33)
    for k, wk, dk in [(3, "wz3", "d3"), (5, "wz5", "d5"),
                      (10, "wz10", "d10")]:
        base = np.mean([p[wk] for p in per_query])
        delta = np.mean([p[dk] for p in per_query])
        print(f"  @{k:<7}{base:>13.4f}{delta:>+14.4f}")
    if np.mean([p["wz10"] for p in per_query]) > 0.85:
        print("\n  READING: nDCG@10 above 0.85 with pools this small means"
              "\n  the metric ranks nearly the whole judged set. Little"
              "\n  headroom for any component to show an effect.")

    # ----------------------------------------------------- C. worst cases
    print("\n" + "=" * 66)
    print("C. WHERE THE FLOOR HURT MOST")
    print("=" * 66)
    for p in sorted(per_query, key=lambda x: x["d10"])[:3]:
        print(f"\n  [{p['id']}]  nDCG@10 {p['d10']:+.3f}   "
              f"priority={p['priority']}  sacrifice={p['sacrifice']}")
        floors = compute_floors(list(p["cands"].values()), p["sacrifice"])
        print(f"  floors: " + ", ".join(f"{k} >= {v:.2f}"
                                        for k, v in floors.items()))
        rows = []
        for i, pid in enumerate(p["fl"]):
            if pid in p["wz"]:
                rows.append((p["wz"].index(pid) + 1, i + 1, pid))
        # Products pushed out of the top-10 entirely by the floor.
        for i, pid in enumerate(p["wz"]):
            if pid not in p["fl"]:
                rows.append((i + 1, 99, pid))
        for was, now, pid in sorted(rows, key=lambda r: r[0] - r[1]):
            if was == now:
                continue
            c = p["cands"][pid]
            sac = ", ".join(
                f"{a}={c['aspects'][a]['score']:.2f}"
                for a in p["sacrifice"] if a in c["aspects"])
            shown = "out" if now == 99 else str(now)
            print(f"    rank {was:>2} -> {shown:<3} label={p['rel'].get(pid,0)}"
                  f"  {sac}  {c['title'][:30]}")


if __name__ == "__main__":
    main()