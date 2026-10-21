"""Fetch reviews for all products via itm_id. Max 5 pages / 50 reviews each.

Checkpointed: products that already have reviews are skipped, so a crash
or re-run never costs credits twice.
"""
import argparse
import os
import pathlib
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from sqlalchemy import func, select

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from core.db import Product, Review, get_session   # noqa: E402

KEY = os.getenv("REEF_API_KEY", "")
URL = "https://api.reefapi.com/flipkart/v1/reviews"

MAX_PAGES = 5
MAX_REVIEWS = 50
MIN_TEXT_LEN = 40
CREDIT_CAP = 150

credits_used = 0


def fetch_page(itm_id: str, page: int) -> tuple[list, bool]:
    """Return (reviews, has_more). Reviews are keyed on itm_id, not product_id."""
    global credits_used
    headers = {"x-api-key": KEY, "Content-Type": "application/json"}
    r = requests.post(URL, headers=headers,
                      json={"itm_id": itm_id, "page": page}, timeout=90)
    if r.status_code != 200:
        print(f"    HTTP {r.status_code}: {r.text[:150]}")
        return [], False

    data = r.json()
    if not data.get("ok"):
        print(f"    error: {(data.get('error') or {}).get('code')}")
        return [], False

    credits_used += 1
    body = data.get("data", {})
    items = body.get("results") or body.get("reviews") or []
    extra = (data.get("meta") or {}).get("extra") or {}
    return items, bool(extra.get("has_more"))


def pick(d: dict, *names, default=None):
    """Field names vary; take the first that exists."""
    for n in names:
        if d.get(n) not in (None, ""):
            return d[n]
    return default


def parse_date(val):
    if not val:
        return None
    if isinstance(val, (int, float)):
        try:
            return datetime.utcfromtimestamp(val / 1000 if val > 1e11 else val)
        except (ValueError, OSError):
            return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%b %Y", "%d %b %Y"):
        try:
            return datetime.strptime(str(val)[:19], fmt)
        except ValueError:
            continue
    return None


def main(refresh: bool = False):
    if not KEY:
        print("ERROR: REEF_API_KEY missing")
        return

    with get_session() as s:
        products = s.execute(select(Product)).scalars().all()

        done = dict(s.execute(
            select(Review.product_id, func.count(Review.id))
            .group_by(Review.product_id)).all())

        existing_texts: dict[str, set[str]] = {}
        if refresh:
            for product_id, review_text in s.execute(
                    select(Review.product_id, Review.text)).all():
                existing_texts.setdefault(product_id, set()).add(
                    (review_text or "")[:120])

        todo = [p for p in products
                if p.itm_id and (refresh or done.get(p.id, 0) == 0)]

        missing = [p for p in products if not p.itm_id]
        if missing:
            print(f"WARNING: {len(missing)} products have no itm_id, skipped\n")

        mode = "refresh (new reviews only)" if refresh else "initial fetch"
        print(f"Mode: {mode}")
        print(f"{len(products)} products, {len(todo)} to fetch\n")
        if refresh:
            print(f"NOTE: ReefAPI calls consume credits (cap: {CREDIT_CAP}).\n")

        total_saved = 0
        for n, p in enumerate(todo, 1):
            if credits_used >= CREDIT_CAP:
                print(f"\nCredit cap ({CREDIT_CAP}) reached. Stopping.")
                break

            print(f"[{n}/{len(todo)}] {p.title[:48]}")
            seen = set(existing_texts.get(p.id, set())) if refresh else set()
            saved = 0

            for page in range(1, MAX_PAGES + 1):
                if saved >= MAX_REVIEWS:
                    break

                items, has_more = fetch_page(p.itm_id, page)
                if not items:
                    break

                if page == 1 and n == 1:
                    print(f"    fields: {list(items[0].keys())}")

                for it in items:
                    if saved >= MAX_REVIEWS:
                        break

                    text = str(pick(it, "text", "review", "body",
                                    "content", default="")).strip()
                    if len(text) < MIN_TEXT_LEN:
                        continue
                    key = text[:120]
                    if key in seen:
                        continue
                    seen.add(key)

                    s.add(Review(
                        product_id=p.id,
                        rating=pick(it, "rating", "stars"),
                        title=str(pick(it, "title", "heading", default=""))[:300],
                        text=text[:5000],
                        helpful_votes=int(pick(it, "upvote", "helpful_votes",
                                               "helpful", default=0) or 0),
                        verified=bool(pick(it, "certified_buyer", "verified",
                                           "is_certified", default=False)),
                        created_at=parse_date(pick(it, "date", "created_at",
                                                   "review_date", "timestamp")),
                    ))
                    saved += 1

                if not has_more:
                    break
                time.sleep(0.3)

            s.commit()
            total_saved += saved
            print(f"    saved {saved}  (credits: {credits_used})")
            time.sleep(0.3)

        print(f"\n{'=' * 55}")
        print(f"reviews saved : {total_saved}")
        print(f"credits used  : {credits_used}")

        n_rev = s.execute(select(func.count(Review.id))).scalar()
        n_prod = s.execute(
            select(func.count(func.distinct(Review.product_id)))).scalar()
        print(f"in database   : {n_rev} reviews across {n_prod} products")
        if n_prod:
            print(f"average       : {n_rev // n_prod} reviews/product")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch product reviews from ReefAPI.")
    parser.add_argument(
        "--refresh", action="store_true",
        help="Check existing products for new reviews; uses ReefAPI credits.",
    )
    args = parser.parse_args()
    main(refresh=args.refresh)
