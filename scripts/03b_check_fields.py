"""Check which review fields actually populated. Zero credits."""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select
from core.db import Review, get_session

with get_session() as s:
    total = s.execute(select(func.count(Review.id))).scalar()
    dated = s.execute(select(func.count(Review.id))
                      .where(Review.created_at.isnot(None))).scalar()
    helpful = s.execute(select(func.count(Review.id))
                        .where(Review.helpful_votes > 0)).scalar()
    verified = s.execute(select(func.count(Review.id))
                         .where(Review.verified.is_(True))).scalar()
    rated = s.execute(select(func.count(Review.id))
                      .where(Review.rating.isnot(None))).scalar()

    print(f"total reviews : {total}")
    print(f"  with date   : {dated}   <- expect 0 (field name was wrong)")
    print(f"  helpful > 0 : {helpful}")
    print(f"  verified    : {verified}")
    print(f"  with rating : {rated}")

    print("\nsample text:")
    for r in s.execute(select(Review).limit(3)).scalars():
        print(f"  [{r.rating}] {r.text[:90]}")