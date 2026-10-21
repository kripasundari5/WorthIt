"""Read the saved catalog and print the Flipkart engine definition.

Pure local file parsing. Makes ZERO API calls, costs ZERO credits.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "discover_catalog.json"


def main():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    engines = data.get("engines", [])
    print(f"Total engines in catalog: {len(engines)}\n")

    # Find anything Flipkart-related.
    matches = [e for e in engines
               if "flipkart" in json.dumps(e).lower()]

    if not matches:
        print("No Flipkart engine found. Indian e-commerce engines present:")
        for e in engines:
            blob = json.dumps(e).lower()
            if any(k in blob for k in
                   ("amazon.in", "india", "myntra", "meesho", "snapdeal")):
                print(f"  - {e.get('name')}: {e.get('title', '')[:90]}")
        return

    for eng in matches:
        print("=" * 70)
        print(f"ENGINE      : {eng.get('name')}")
        print(f"BASE PATH   : {eng.get('base_path')}")
        print(f"VERSION     : {eng.get('version')}")
        print(f"CATEGORY    : {eng.get('category', {}).get('title')}")
        print(f"\nTITLE:\n{eng.get('title', '')}\n")

        actions = eng.get("actions", [])
        print(f"ACTIONS ({len(actions)}):")
        print("=" * 70)

        for a in actions:
            name = a.get("name")
            base = eng.get("base_path", "")
            print(f"\n--- {name}")
            print(f"    FULL PATH : POST {base}/{name}")

            # Credit cost may be named several ways; show whatever exists.
            for key in ("price", "credits", "cost", "price_credits",
                        "unit_price", "pricing"):
                if key in a:
                    print(f"    {key.upper():<10}: {a[key]}")

            desc = a.get("description", "")
            if desc:
                print(f"    DESC      : {desc[:400]}")

            params = (a.get("params") or a.get("parameters")
                      or a.get("input") or a.get("schema"))
            if params:
                print(f"    PARAMS    : {json.dumps(params, indent=6)[:1200]}")

        # Save just the Flipkart slice for easy reference.
        out = ROOT / "data" / "flipkart_engine.json"
        out.write_text(json.dumps(eng, indent=2))
        print(f"\n\nSaved full definition to: {out}")


if __name__ == "__main__":
    main()
