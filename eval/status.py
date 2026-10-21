"""Show labelling progress. Reads only, changes nothing."""
import json, pathlib
from collections import Counter

p = pathlib.Path(__file__).parent / "queries.json"
qs = json.loads(p.read_text())

done = [q for q in qs if q.get("relevance")]
print(f"labelled: {len(done)}/{len(qs)}")

dist = Counter()
for q in done:
    dist.update(q["relevance"].values())
total = sum(dist.values())
print(f"judgements: {total}")
for lab in sorted(dist, reverse=True):
    pct = 100 * dist[lab] / total if total else 0
    print(f"  {lab}: {dist[lab]:>3}  ({pct:.0f}%)")

for q in done:
    print(f"\n[{q['id']}] {q['query'][:62]}")
    for pid, lab in sorted(q["relevance"].items(), key=lambda x: -x[1]):
        print(f"    {lab}  {pid}")