"""Generate the evaluation query set. ZERO credits, no API calls.

Every query pairs ONE priority aspect with ONE explicitly sacrificed aspect
across three budget bands. Each generated query is validated against the
parser before being written: a query the parser misreads would silently
corrupt the whole evaluation, and that failure is invisible downstream.

Output: eval/queries.json  (unlabelled -- run eval/label.py next)
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


from dotenv import load_dotenv                       # noqa: E402
load_dotenv(ROOT / ".env")

from core.parser import _keyword_fallback as parse   # noqa: E402

OUT = ROOT / "eval" / "queries.json"

# Phrasing for each aspect in the two grammatical positions. Kept close to
# how people actually type, but constrained to vocabulary the parser knows.
PRIORITY_PHRASE = {
    "performance":   "great performance",
    "battery_life":  "good battery life",
    "display":       "a good display",
    "thermals":      "good thermals",
    "build_quality": "solid build quality",
    "portability":   "low weight",
}

SACRIFICE_PHRASE = {
    "performance":   "performance can be average",
    "battery_life":  "dont mind weak battery life",
    "display":       "dont mind a basic display",
    "thermals":      "dont mind heating",
    "build_quality": "build quality can be average",
    "portability":   "dont mind the weight",
}

# Pairs chosen for genuine physical tension, not arbitrary combinations.
# A trade-off the hardware does not actually force is not worth testing.
PAIRS = [
    ("performance", "battery_life"),
    ("performance", "thermals"),
    ("performance", "build_quality"),
    ("performance", "display"),
    ("battery_life", "performance"),
    ("battery_life", "display"),
    ("battery_life", "thermals"),
    ("display", "battery_life"),
    ("display", "build_quality"),
    ("display", "performance"),
    ("build_quality", "performance"),
    ("thermals", "performance"),
]

BUDGETS = [50000, 80000, 120000]


def build(priority: str, sacrifice: str, budget: int) -> str:
    return (f"laptop under {budget} with {PRIORITY_PHRASE[priority]}, "
            f"{SACRIFICE_PHRASE[sacrifice]}")


def validate(text: str, priority: str, sacrifice: str, budget: int):
    """Return (ok, problems)."""
    q = parse(text)
    problems = []

    if q.constraints.max_price != float(budget):
        problems.append(f"budget parsed as {q.constraints.max_price}")

    prios = q.priorities()
    sacs = q.sacrifices()

    if priority not in prios:
        problems.append(f"'{priority}' not tagged priority (got {list(prios)})")
    if sacrifice not in sacs:
        problems.append(f"'{sacrifice}' not tagged sacrifice (got {sacs})")
    if priority in sacs:
        problems.append(f"'{priority}' wrongly tagged sacrifice")
    if sacrifice in prios:
        problems.append(f"'{sacrifice}' wrongly tagged priority")

    return (not problems), problems


def main():
    queries, rejected = [], []

    for priority, sacrifice in PAIRS:
        for budget in BUDGETS:
            text = build(priority, sacrifice, budget)
            ok, problems = validate(text, priority, sacrifice, budget)

            if ok:
                queries.append({
                    "id": f"q{len(queries) + 1:03d}",
                    "query": text,
                    "priority": priority,
                    "sacrifice": sacrifice,
                    "budget": budget,
                    "relevance": {},          # filled by eval/label.py
                })
            else:
                rejected.append((text, problems))

    print(f"generated : {len(queries)}")
    print(f"rejected  : {len(rejected)}")

    for text, problems in rejected:
        print(f"\n  REJECTED: {text}")
        for p in problems:
            print(f"      - {p}")

    if not queries:
        print("\nNothing usable. Check ALIASES in core/parser.py.")
        return

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(queries, indent=2))
    print(f"\nwrote {OUT}")

    print("\nsample:")
    for q in queries[:4]:
        print(f"  [{q['id']}] {q['query']}")
        print(f"          priority={q['priority']}  sacrifice={q['sacrifice']}")


if __name__ == "__main__":
    main()