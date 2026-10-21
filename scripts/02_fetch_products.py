"""Fetch 25 laptops from Flipkart via ReefAPI. Costs 2 credits.

Two searches across different price bands so the candidate pool has
spread -- a pool clustered at one price makes the floor percentile
meaningless once a price filter is applied.
"""
import os
import pathlib
import sys
import time

import requests
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from core.db import Product, get_session   # noqa: E402

KEY = os.getenv("REEF_API_KEY", "")
URL = "https://api.reefapi.com/flipkart/v1/search"

TARGET = 25
MIN_REVIEWS = 15          # need enough text for stable aspect scores

SEARCHES = [
    "laptop under 50000",
    "gaming laptop",
]


def search(query: str) -> list[dict]:
    headers = {"x-api-key": KEY, "Content-Type": "application/json"}
    r = requests.post(URL, headers=headers,
                      json={"query": query}, timeout=90)
    if r.status_code != 200:
        print(f"  HTTP {r.status_code}: {r.text[:200]}")
        return []
    data = r.json()
    if not data.get("ok"):
        print(f"  error: {data.get('error')}")
        return []
    return data.get("data", {}).get("results", [])


def is_laptop(item: dict) -> bool:
    cat = (item.get("analytics") or {}).get("category", "")
    return "laptop" in cat.lower()


def main():
    if not KEY:
        print("ERROR: REEF_API_KEY missing from .env")
        return

    pool: dict[str, dict] = {}

    for q in SEARCHES:
        print(f"\nSearching: {q!r}")
        results = search(q)
        print(f"  {len(results)} returned")

        kept = 0
        for item in results:
            pid = item.get("product_id")
            if not pid or pid in pool:
                continue
            if not is_laptop(item):
                continue
            if (item.get("review_count") or 0) < MIN_REVIEWS:
                continue
            if not item.get("price"):
                continue
            pool[pid] = item
            kept += 1
        print(f"  {kept} usable (laptop, >={MIN_REVIEWS} reviews, has price)")
        time.sleep(1)          # rate limit is 30 req / 3 s; be polite

    if not pool:
        print("\nNothing usable found. Try different search terms.")
        return

    # Prefer products with more reviews -- better aspect coverage.
    chosen = sorted(pool.values(),
                    key=lambda x: x.get("review_count") or 0,
                    reverse=True)[:TARGET]

    print(f"\nSelected {len(chosen)} products")
    print(f"{'price':>8}  {'reviews':>7}  title")
    print("-" * 70)

    with get_session() as s:
        for item in chosen:
            print(f"{item['price']:>8}  {item.get('review_count', 0):>7}  "
                  f"{item['title'][:50]}")
            s.merge(Product(
                id=item["product_id"],
                itm_id=item.get("itm_id"),
                title=item["title"][:500],
                brand=(item["title"].split()[0] if item.get("title") else None),
                price=float(item["price"]),
                avg_rating=item.get("rating"),
                rating_count=item.get("rating_count") or 0,
                review_count=item.get("review_count") or 0,
                image_url=item.get("image"),
                category="Laptops",
            ))
        s.commit()

    prices = [c["price"] for c in chosen]
    total_reviews = sum(c.get("review_count") or 0 for c in chosen)
    print(f"\nprice range : Rs {min(prices):,} - Rs {max(prices):,}")
    print(f"text reviews available: {total_reviews}")
    print(f"credits used: {len(SEARCHES)}")


if __name__ == "__main__":
    main()
