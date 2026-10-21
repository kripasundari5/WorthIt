"""ONE Flipkart search call. Costs 1 credit.

Purpose: see the real response shape before writing the bulk loader.
Does NOT fetch product details or reviews.
"""
import json
import os
import pathlib

import requests
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

KEY = os.getenv("REEF_API_KEY", "")
URL = "https://api.reefapi.com/flipkart/v1/search"
OUT = ROOT / "data"
OUT.mkdir(exist_ok=True)

QUERY = "gaming laptop"


def main():
    if not KEY:
        print("ERROR: REEF_API_KEY not found in .env")
        return

    headers = {"x-api-key": KEY, "Content-Type": "application/json"}
    payload = {"query": QUERY}

    print(f"POST {URL}")
    print(f"payload: {payload}\n")

    r = requests.post(URL, headers=headers, json=payload, timeout=60)
    print(f"HTTP {r.status_code}")

    if r.status_code != 200:
        print(f"body: {r.text[:800]}")
        return

    data = r.json()
    (OUT / "test_search.json").write_text(json.dumps(data, indent=2))

    print(f"ok    : {data.get('ok')}")
    print(f"meta  : {json.dumps(data.get('meta', {}), indent=2)}")

    if data.get("error"):
        print(f"error : {data['error']}")
        return

    # Find the list of products wherever it lives.
    body = data.get("data", data)
    items = None
    if isinstance(body, list):
        items = body
    elif isinstance(body, dict):
        for k in ("products", "results", "items", "data"):
            if isinstance(body.get(k), list):
                items, key = body[k], k
                print(f"\nproducts found under key: '{k}'")
                break

    if not items:
        print("\nCould not locate a product list. Top-level keys:")
        print(list(body.keys()) if isinstance(body, dict) else type(body))
        print("\nFull response saved to data/test_search.json")
        return

    print(f"\nproducts returned: {len(items)}")
    print("\n--- FIRST PRODUCT (all fields) ---")
    print(json.dumps(items[0], indent=2)[:2500])

    print("\n--- FIELD NAMES ---")
    for k, v in items[0].items():
        preview = str(v)[:60]
        print(f"  {k:24s} ({type(v).__name__:5s}) = {preview}")

    print(f"\nSaved to {OUT / 'test_search.json'}")


if __name__ == "__main__":
    main()
