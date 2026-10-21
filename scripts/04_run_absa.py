"""Batch ABSA over unprocessed reviews, then aggregate. ZERO credits."""
import sys, pathlib, argparse
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from core.absa import extract_batch
from core.aggregate import aggregate_product
from core.db import AspectMention, Review, get_session

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=32)
    args = ap.parse_args()

    with get_session() as s:
        reviews = s.execute(
            select(Review).where(Review.processed == False)  # noqa: E712
        ).scalars().all()
        print(f"{len(reviews)} reviews to process")

        for i in range(0, len(reviews), args.batch):
            chunk = reviews[i:i + args.batch]
            for review, mentions in zip(chunk, extract_batch(
                    [r.text for r in chunk])):
                for aspect, sentiment, evidence in mentions:
                    s.add(AspectMention(
                        review_id=review.id, product_id=review.product_id,
                        aspect=aspect, sentiment=sentiment, evidence=evidence))
                review.processed = True
            s.commit()
            print(f"  {min(i + args.batch, len(reviews))}/{len(reviews)}")

        print("Aggregating...")
        pids = s.execute(
            select(AspectMention.product_id).distinct()).scalars().all()
        for pid in pids:
            aggregate_product(s, pid)
    print("Done.")