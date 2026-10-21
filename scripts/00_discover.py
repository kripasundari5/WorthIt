"""Free discovery. Costs ZERO credits.

Finds the real endpoint paths and parameter names for the Flipkart engine
so we don't waste credits guessing.
"""
import json
import os
import pathlib
import sys

import requests
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

KEY = os.getenv("REEF_API_KEY", "")
BASE = "https://api.reefapi.com"
OUT = ROOT / "data"
OUT.mkdir(exist_ok=True)


def show(label, obj, limit=3000):
    text = json.dumps(obj, indent=2)
    print(f"\n{'=' * 60}\n{label}\n{'=' * 60}")
    print(text[:limit])
    if len(text) > limit:
        print(f"\n... truncated ({len(text)} chars total)")


def try_get(path, params=None):
    """Discovery endpoints are keyless, but send the key if we have one."""
    headers = {}
    if KEY:
        headers["Authorization"] = f"Bearer {KEY}"
        headers["x-api-key"] = KEY
    try:
        r = requests.get(f"{BASE}{path}", headers=headers,
                         params=params or {}, timeout=60)
        print(f"GET {path} -> HTTP {r.status_code}")
        if r.status_code == 200:
            return r.json()
        print(f"   body: {r.text[:300]}")
    except requests.RequestException as e:
        print(f"GET {path} -> FAILED: {e}")
    return None


if __name__ == "__main__":
    if not KEY:
        print("WARNING: REEF_API_KEY not found in .env "
              "(discovery may still work)\n")
    else:
        print(f"Key loaded: {KEY[:10]}...\n")

    # The catalog lists every engine. We want the Flipkart one.
    catalog = try_get("/v1/catalog") or try_get("/catalog")
    if catalog:
        show("CATALOG (searching for flipkart)", catalog, 2000)
        (OUT / "discover_catalog.json").write_text(json.dumps(catalog, indent=2))

    # The engine schema lists its actions and parameters.
    schema = (try_get("/v1/engines/flipkart")
              or try_get("/flipkart/v1/schema")
              or try_get("/v1/schema/flipkart"))
    if schema:
        show("FLIPKART ENGINE SCHEMA", schema, 4000)
        (OUT / "discover_flipkart.json").write_text(json.dumps(schema, indent=2))

    if not catalog and not schema:
        print("\nNo discovery endpoint responded. That's fine -- it means the "
              "paths differ from my guesses. Check the docs page in your "
              "ReefAPI dashboard and tell me what the base URL and auth "
              "header look like.")
    else:
        print(f"\nSaved to {OUT}")