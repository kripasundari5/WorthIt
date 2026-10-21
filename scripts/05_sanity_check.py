"""Manual spot-check. ZERO credits. DO NOT SKIP.

Bad extraction is silent: the pipeline runs, numbers appear, and every
score downstream is meaningless.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select
from core.config import ASPECT_LABELS
from core.db import AspectMention, AspectScore, Product, Review, get_session

with get_session() as s:
    print("=" * 64)
    for model, name in [(Product, "products"), (Review, "reviews"),
                        (AspectMention, "mentions"), (AspectScore, "scores")]:
        n = s.execute(select(func.count()).select_from(model)).scalar()
        print(f"  {name:10s} {n}")

    print("\nSCORE SPREAD PER ASPECT  (need variance, not all ~0.5)")
    rows = s.execute(
        select(AspectScore.aspect, func.count(), func.min(AspectScore.score),
               func.avg(AspectScore.score), func.max(AspectScore.score))
        .group_by(AspectScore.aspect)).all()
    for aspect, n, lo, avg, hi in sorted(rows, key=lambda r: -r[1]):
        print(f"  {ASPECT_LABELS.get(aspect, aspect):22s} n={n:<3} "
              f"min={lo:.2f} avg={avg:.2f} max={hi:.2f}")

    print("\nTOP 3 PRODUCTS -- VERIFY THESE BY HAND")
    prods = s.execute(
        select(Product).join(AspectScore, AspectScore.product_id == Product.id)
        .group_by(Product.id)
        .order_by(func.count(AspectScore.id).desc()).limit(3)).scalars().all()

    for p in prods:
        print(f"\n  {p.title[:62]}\n  Rs {p.price:,.0f}")
        for sc in s.execute(
                select(AspectScore).where(AspectScore.product_id == p.id)
                .order_by(AspectScore.mentions.desc())).scalars():
            bar = "#" * int(sc.score * 20)
            print(f"    {ASPECT_LABELS.get(sc.aspect, sc.aspect):20s} "
                  f"{sc.score:.2f} {bar:<20s} n={sc.mentions}")

    print("\nEVIDENCE SAMPLES -- does the sentiment match the text?")
    for aspect in ["performance", "thermals", "battery_life"]:
        print(f"\n  [{aspect}]")
        for m in s.execute(
                select(AspectMention).where(AspectMention.aspect == aspect)
                .order_by(AspectMention.sentiment.desc()).limit(2)).scalars():
            print(f"    {m.sentiment:+.2f}  {(m.evidence or '')[:95]}")
        for m in s.execute(
                select(AspectMention).where(AspectMention.aspect == aspect)
                .order_by(AspectMention.sentiment.asc()).limit(2)).scalars():
            print(f"    {m.sentiment:+.2f}  {(m.evidence or '')[:95]}")