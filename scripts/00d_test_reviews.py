"""ONE Flipkart reviews call. Costs 1 credit.

We need three things: reviews per page, the field names, and how
pagination is signalled. Nothing else.
"""
import json
import os
import pathlib

import requests
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

KEY = os.getenv("REEF_API_KEY", "")
URL = "https://api.reefapi.com/flipkart/v1/reviews"
OUT = ROOT / "data"

# The ASUS TUF from our search -- 221 text reviews, plenty to page through.
ITM_ID = "itm2a48b3e7ebd9c"


def main():
    if not KEY:
        print("ERROR: REEF_API_KEY not found in .env")
        return

    headers = {"x-api-key": KEY, "Content-Type": "application/json"}
    payload = {"itm_id": ITM_ID, "page": 1}

    print(f"POST {URL}")
    print(f"payload: {payload}\n")

    r = requests.post(URL, headers=headers, json=payload, timeout=90)
    print(f"HTTP {r.status_code}")

    if r.status_code != 200:
        print(f"body: {r.text[:800]}")
        print("\nIf this is a param error, the reviews action may want "
              "'url' or 'itm_id' instead of 'product_id'.")
        return

    data = r.json()
    (OUT / "test_reviews.json").write_text(json.dumps(data, indent=2))

    print(f"ok    : {data.get('ok')}")
    print(f"meta  : {json.dumps(data.get('meta', {}), indent=2)}")

    if data.get("error"):
        print(f"error : {data['error']}")
        return

    body = data.get("data", data)
    items = None
    if isinstance(body, list):
        items = body
    elif isinstance(body, dict):
        for k in ("reviews", "results", "items", "data"):
            if isinstance(body.get(k), list):
                items = body[k]
                print(f"\nreviews found under key: '{k}'")
                break

    if not items:
        print("\nCould not locate a review list. Top-level keys:")
        print(list(body.keys()) if isinstance(body, dict) else type(body))
        return

    print(f"\n*** REVIEWS PER PAGE: {len(items)} ***")

    print("\n--- FIRST REVIEW (all fields) ---")
    print(json.dumps(items[0], indent=2)[:2000])

    print("\n--- FIELD NAMES ---")
    for k, v in items[0].items():
        print(f"  {k:22s} ({type(v).__name__:5s}) = {str(v)[:60]}")

    # Sanity: is the review text long enough for ABSA?
    lengths = [len(str(x.get("text") or x.get("review") or
                       x.get("body") or "")) for x in items]
    if any(lengths):
        print(f"\ntext length: min={min(lengths)} "
              f"max={max(lengths)} avg={sum(lengths) // len(lengths)}")

    print(f"\nSaved to {OUT / 'test_reviews.json'}")


if __name__ == "__main__":
    main()

