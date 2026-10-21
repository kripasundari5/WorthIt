"""Find the products where the floor actually changes the ranking."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from core.db import get_session
from core.parser import _keyword_fallback as parse
from core.ranker import rank
from core.retrieve import fetch_candidates

QUERY = "laptop under 80000 with great performance, dont mind heating"

q = parse(QUERY)
with get_session() as s:
    cands = fetch_candidates(s, q.constraints)

off, _ = rank(cands, q, use_floor=False, use_price=True, top_k=50)
on, floors = rank(cands, q, use_floor=True, use_price=True, top_k=50)

pos_off = {c["product_id"]: i for i, c in enumerate(off, 1)}
print(f"floor = {floors.get('thermals', 0):.3f}\n")
print(f"{'off':>4} {'on':>4} {'move':>5}  {'perf':>5} {'therm':>6} {'pen':>6}  title")
print("-" * 82)
for i, c in enumerate(on, 1):
    was = pos_off[c["product_id"]]
    move = was - i
    perf = c["aspects"].get("performance", {}).get("score", 0)
    th = c["aspects"].get("thermals")
    ths = f"{th['score']:.2f}" if th else "  --"
    mark = "  <<<" if move != 0 else ""
    print(f"{was:>4} {i:>4} {move:>+5}  {perf:>5.2f} {ths:>6} "
          f"{c['floor_penalty']:>6.3f}  {c['title'][:36]}{mark}")