"""Label the evaluation queries. ZERO credits, no API calls.

Uses POOLING, the standard IR approach: for each query, take the union of
the top-N from every system under test and label only those. Labelling all
20 candidates for all 36 queries would be 720 judgements; pooling cuts it
to roughly 300 without biasing toward any one system.

Deliberately does NOT show you the system's rank or utility. You judge the
product on its price and aspect scores alone, so the label is about the
laptop rather than about what the ranker already decided.

Resumable: saves after every query. Ctrl-C and come back.

Scale:
  3 = excellent   strong on the priority aspect AND acceptable elsewhere
  2 = good        solid on the priority aspect, minor weaknesses
  1 = marginal    mediocre, or a real weakness on something that matters
  0 = bad         fails the priority aspect, or broken on the sacrificed one
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv                       # noqa: E402
load_dotenv(ROOT / ".env")

from core.config import ASPECT_LABELS, RANKING_ASPECTS   # noqa: E402
from core.db import get_session                      # noqa: E402
from core.parser import _keyword_fallback as parse   # noqa: E402
from core.ranker import rank                         # noqa: E402
from core.retrieve import fetch_candidates           # noqa: E402

QUERIES = ROOT / "eval" / "queries.json"
POOL_DEPTH = 8          # top-N from each system


def build_pool(cands, parsed):
    """Union of top-N from each system under test.

    Pooling from all systems, not just ours, is what keeps the evaluation
    fair -- labelling only our own top results would guarantee we win.
    """
    pool = {}
    runs = [
        rank(cands, parsed, use_floor=True, use_price=True,
             top_k=POOL_DEPTH)[0],
        rank(cands, parsed, use_floor=False, use_price=True,
             top_k=POOL_DEPTH)[0],
        rank(cands, parsed, use_floor=False, use_price=False,
             top_k=POOL_DEPTH)[0],
    ]
    for run in runs:
        for c in run:
            pool[c["product_id"]] = c

    # Rating-sort baseline also contributes to the pool.
    for c in sorted(cands, key=lambda x: x.get("avg_rating") or 0,
                    reverse=True)[:POOL_DEPTH]:
        pool[c["product_id"]] = c

    return list(pool.values())


def show(c, parsed):
    priority = list(parsed.priorities())
    sacrifice = parsed.sacrifices()

    print(f"\n  {c['title'][:66]}")
    print(f"  Rs {c['price']:,.0f}"
          f"   flipkart rating {c.get('avg_rating') or '--'}")

    for a in RANKING_ASPECTS:
        e = c["aspects"].get(a)
        label = ASPECT_LABELS.get(a, a)
        if not e:
            print(f"    {label:22s}   no data")
            continue
        tag = ""
        if a in priority:
            tag = "  <-- PRIORITY"
        elif a in sacrifice:
            tag = "  <-- sacrificed"
        bar = "#" * int(e["score"] * 18)
        print(f"    {label:22s} {e['score']:.2f} {bar:<18s} "
              f"n={e['mentions']}{tag}")

    for a in sacrifice:
        e = c["aspects"].get(a)
        if not e:
            continue
        if e["score"] < 0.15:
            print(f"    >> RUBRIC: sacrificed {a} = {e['score']:.2f} "
                  f"(<0.15) -> CAP AT 1")
        elif e["score"] < 0.35:
            print(f"    >> RUBRIC: sacrificed {a} = {e['score']:.2f} "
                  f"(0.15-0.34) -> DROP ONE LEVEL")

    for a in priority:
        e = c["aspects"].get(a)
        if e and e["mentions"] < 2:
            print(f"    >> RUBRIC: priority {a} has {e['mentions']} "
                  f"mention -> CAP AT 2")
        if not e:
            print(f"    >> RUBRIC: no data on priority {a} -> 0")

    SHORT = {"performance": "Perf", "battery_life": "Batt", "display": "Disp",
         "thermals": "Heat", "build_quality": "Buil", "portability": "Port"}


def _cell(c, a):
    """score/mentions, fixed width 8 so columns never collide."""
    e = c["aspects"].get(a)
    if not e:
        return "   --   "
    return f"{e['score']:.2f}/{e['mentions']:<3d}"


def _rubric_hint(c, priority, sacrifice):
    """Flag which rubric steps apply. Does NOT compute a label."""
    hints = []
    for a in priority:
        e = c["aspects"].get(a)
        if not e:
            hints.append(f"no {SHORT.get(a, a)} -> 0")
        elif e["mentions"] < 2:
            hints.append(f"{SHORT.get(a, a)} n=1 -> cap 2")
    for a in sacrifice:
        e = c["aspects"].get(a)
        if not e:
            continue
        if e["score"] < 0.15:
            hints.append(f"{SHORT.get(a, a)} <.15 -> cap 1")
        elif e["score"] < 0.35:
            hints.append(f"{SHORT.get(a, a)} <.35 -> drop 1")
    for a in RANKING_ASPECTS:
        if a in priority or a in sacrifice:
            continue
        e = c["aspects"].get(a)
        if e and e["score"] < 0.20:
            hints.append(f"{SHORT.get(a, a)} low -> drop 1")
    return "; ".join(hints)


def _render_table(pool, priority, sacrifice):
    hdr = ["  # ", "Price        "]
    for a in RANKING_ASPECTS:
        mark = "*" if a in priority else ("^" if a in sacrifice else " ")
        hdr.append(f"{SHORT.get(a, a) + mark:<8}")
    print("".join(hdr) + "Title")
    print("-" * 118)
    for i, c in enumerate(pool, 1):
        row = [f"{i:>3} ", f"Rs {c['price']:>9,.0f} "]
        for a in RANKING_ASPECTS:
            row.append(f"{_cell(c, a):<8}")
        row.append(c["title"][:26])
        print("".join(row))
    print("-" * 118)
    print("  * = priority    ^ = sacrificed    score/mentions\n")

    notes = [(i, _rubric_hint(c, priority, sacrifice))
             for i, c in enumerate(pool, 1)]
    notes = [(i, h) for i, h in notes if h]
    if notes:
        print("  RUBRIC NOTES")
        for i, h in notes:
            print(f"   {i:>3}  {h}")


def _parse_labels(raw, n):
    """Return (dict index->label, error). 's' skips a slot."""
    toks = raw.replace(",", " ").split()
    if len(toks) != n:
        return None, f"expected {n} values, got {len(toks)}"
    out = {}
    for i, t in enumerate(toks):
        if t.lower() == "s":
            continue
        if t not in ("0", "1", "2", "3"):
            return None, f"position {i + 1}: '{t}' is not 0-3 or s"
        out[i] = int(t)
    return out, None


def label_batch(pool, parsed):
    """Table view, one input line, confirm before returning. None = abort."""
    priority = list(parsed.priorities())
    sacrifice = parsed.sacrifices()

    while True:
        _render_table(pool, priority, sacrifice)
        print(f"\n  Enter {len(pool)} labels, space separated "
              f"(0-3, or s to skip). 'q' aborts this query.")
        raw = input("  > ").strip()

        if raw.lower() == "q":
            return None

        picked, err = _parse_labels(raw, len(pool))
        if err:
            print(f"  !! {err}\n")
            continue

        print("\n  REVIEW")
        for i, c in enumerate(pool):
            lab = picked.get(i)
            shown = lab if lab is not None else "skip"
            print(f"   {shown}  {c['title'][:58]}")

        ok = input("\n  save these? [y/n] ").strip().lower()
        if ok == "y":
            return {pool[i]["product_id"]: lab for i, lab in picked.items()}
        print("  re-entering\n")
                
def main():
    queries = json.loads(QUERIES.read_text())
    todo = [q for q in queries if not q.get("relevance")]

    print(f"{len(queries)} queries, {len(todo)} still unlabelled")
    if not todo:
        print("All labelled. Run eval/run_eval.py next.")
        return

    print("\n  3 = excellent   2 = good   1 = marginal   0 = bad")
    print("  s = skip product    q = save and quit\n")

    with get_session() as session:
        for qi, q in enumerate(todo, 1):
            parsed = parse(q["query"])
            cands = fetch_candidates(session, parsed.constraints)
            if not cands:
                print(f"[{q['id']}] no candidates, skipping")
                q["relevance"] = {"__none__": 0}
                continue

            pool = build_pool(cands, parsed)
            # Stable order, independent of any system's ranking.
            pool.sort(key=lambda c: c["price"])

            print(f"\n{'=' * 70}")
            print(f"[{qi}/{len(todo)}]  {q['query']}")
            print(f"  priority: {q['priority']}   "
                  f"sacrifice: {q['sacrifice']}   "
                  f"{len(pool)} to label")
            print("=" * 70)

            rel = {}
            quit_now = False
            for c in pool:
                show(c, parsed)
                while True:
                    ans = input("    label [0-3/s/q]: ").strip().lower()
                    if ans in ("0", "1", "2", "3"):
                        rel[c["product_id"]] = int(ans)
                        break
                    if ans == "s":
                        break
                    if ans == "q":
                        quit_now = True
                        break
                    print("    enter 0, 1, 2, 3, s or q")
                if quit_now:
                    break

            if rel:
                q["relevance"] = rel
            QUERIES.write_text(json.dumps(queries, indent=2))

            if quit_now:
                print(f"\nSaved. {sum(1 for x in queries if x.get('relevance'))}"
                      f"/{len(queries)} labelled.")
                return

    QUERIES.write_text(json.dumps(queries, indent=2))
    print(f"\nDone. {sum(1 for x in queries if x.get('relevance'))}"
          f"/{len(queries)} labelled.")


if __name__ == "__main__":
    main()