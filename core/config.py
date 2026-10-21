"""Central configuration. Everything tunable lives here."""
import os

DB_URL = os.getenv(
    "DB_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/tradeoff"
)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-6")

ASPECTS = [
    "performance", "battery_life", "portability", "thermals",
    "display", "build_quality", "value",
]

ASPECT_LABELS = {
    "performance": "Performance",
    "battery_life": "Battery life",
    "portability": "Portability / weight",
    "thermals": "Heat & fan noise",
    "display": "Display",
    "build_quality": "Build quality",
    "value": "Value for money",
}

# Aspects used for RANKING. 'value' is excluded: lexicon ABSA showed severe
# positive saturation (min 0.50, mean 0.88), so it cannot discriminate
# between products. It stays in ASPECTS for display and in the database.
RANKING_ASPECTS = [
    "performance", "battery_life", "display", "thermals",
    "build_quality", "portability",
]

# Price efficiency: objective, computed from the price column, not from
# review text. Replaces the unusable value-sentiment signal.
USE_PRICE_EFFICIENCY = os.getenv("USE_PRICE_EFFICIENCY", "1") not in ("0", "false", "False")
PRICE_WEIGHT = float(os.getenv("PRICE_WEIGHT", "0.20"))

# Verified on 25 Flipkart laptops, 493 reviews (floor sweep, scripts/07).
# Below percentile 20 the floor never binds; above 50 it penalises half the
# pool. 35 separates the broken thermals cluster (0.00-0.00) from the
# acceptable one (0.33+). MIN_MENTIONS=1 is required because aspect mentions
# average 1-2 per product at this dataset size.
FLOOR_PERCENTILE = float(os.getenv("FLOOR_PERCENTILE", "35"))
FLOOR_LAMBDA = float(os.getenv("FLOOR_LAMBDA", "3.0"))
PRIORITY_GAMMA = float(os.getenv("PRIORITY_GAMMA", "0.7"))

TIME_DECAY_HALFLIFE_DAYS = float(os.getenv("TIME_DECAY_HALFLIFE_DAYS", "365"))
MIN_MENTIONS = int(os.getenv("MIN_MENTIONS", "1"))
TOP_K = int(os.getenv("TOP_K", "10"))


FLOOR_GUARD = os.getenv("FLOOR_GUARD", "0").strip().lower() in ("1", "true", "yes", "on")