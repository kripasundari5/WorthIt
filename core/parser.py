"""Free text -> ParsedQuery.

Deliberately thin -- plumbing, not the contribution. The one thing it MUST
get right is separating 'sacrifice' from 'priority'.
"""
from __future__ import annotations

import json
import re

from core.config import ANTHROPIC_API_KEY, ASPECTS, LLM_MODEL
from core.schemas import AspectPreference, HardConstraints, ParsedQuery

SYSTEM = f"""You extract structured shopping preferences from a query.

Valid aspects: {", ".join(ASPECTS)}

Classify every aspect the user mentions as exactly one of:
- "priority": they want this to be good. Assign weight 1-3 by emphasis.
- "sacrifice": they EXPLICITLY said they will accept this being worse
  ("don't mind slow charging", "camera can be average"). NOT the same as
  simply not mentioning it.
- "indifferent": mentioned but explicitly stated as not mattering at all.

Aspects not mentioned at all: omit entirely.

Return ONLY a JSON object, no fences, no commentary:
{{"constraints": {{"max_price": null, "min_price": null,
  "brands_include": [], "brands_exclude": []}},
  "preferences": [{{"aspect": "camera", "kind": "priority", "weight": 2.0}}]}}"""

SACRIFICE_CUES = [
    "don't mind", "dont mind", "do not mind", "ok if", "okay if",
    "can compromise", "compromise on", "willing to compromise", "fine if",
    "not bothered", "can be average", "can be worse", "doesn't matter",
    "dosent matter", "sacrifice", "even if", "no issue",
]

ALIASES = {
    "camera": ["camera", "photo", "picture", "selfie"],
    "battery_life": ["battery life", "battery backup", "battery"],
    "charging_speed": ["charging", "charge", "charger"],
    "display": ["display", "screen"],
    "performance": ["performance", "processor", "gaming", "speed", "lag"],
    "thermals": ["heat", "thermal", "overheat"],
    "build_quality": ["build", "durability", "sturdy"],
    "audio": ["audio", "sound", "speaker"],
    "software": ["software", "bloatware", "ui"],
    "value": ["value for money", "worth it"],
}


def _parse_price(text: str) -> tuple[float | None, float | None]:
    t = text.lower().replace(",", "")
    mn = mx = None
    m = re.search(r"(?:under|below|less than|upto|up to|within)\s*"
                  r"(?:rs\.?|inr|₹|\$)?\s*(\d+(?:\.\d+)?)\s*(k|thousand)?", t)
    if m:
        mx = float(m.group(1)) * (1000 if m.group(2) else 1)
    m = re.search(r"(?:above|over|more than|at least)\s*"
                  r"(?:rs\.?|inr|₹|\$)?\s*(\d+(?:\.\d+)?)\s*(k|thousand)?", t)
    if m:
        mn = float(m.group(1)) * (1000 if m.group(2) else 1)
    return mn, mx


def _keyword_fallback(text: str) -> ParsedQuery:
    """No-LLM path. Keeps the demo alive if the API is down.

    Splits into clauses first. A cue like "don't mind" must attach to the
    aspect in ITS OWN clause -- a character window around the aspect leaks
    cues across clauses and mislabels priorities as sacrifices.
    """
    t = text.lower()
    mn, mx = _parse_price(t)

    clauses = [c.strip() for c in re.split(r",|;|\band\b|\bbut\b", t) if c.strip()]

    prefs: dict[str, AspectPreference] = {}
    for clause in clauses:
        has_cue = any(c in clause for c in SACRIFICE_CUES)
        for aspect, keys in ALIASES.items():
            if aspect in prefs:
                continue
            if any(k in clause for k in keys):
                kind = "sacrifice" if has_cue else "priority"
                prefs[aspect] = AspectPreference(
                    aspect=aspect, kind=kind,
                    weight=0.0 if kind == "sacrifice" else 1.5)

    return ParsedQuery(raw_text=text,
                       constraints=HardConstraints(max_price=mx, min_price=mn),
                       preferences=list(prefs.values()))


def parse_query(text: str) -> ParsedQuery:
    if not ANTHROPIC_API_KEY:
        return _keyword_fallback(text)
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=LLM_MODEL, max_tokens=800, system=SYSTEM,
            messages=[{"role": "user", "content": text}])
        raw = "".join(b.text for b in resp.content if b.type == "text")
        raw = re.sub(r"```(?:json)?|```", "", raw).strip()
        data = json.loads(raw)
        prefs = [AspectPreference(**p) for p in data.get("preferences", [])
                 if p.get("aspect") in ASPECTS]
        return ParsedQuery(
            raw_text=text,
            constraints=HardConstraints(**data.get("constraints", {})),
            preferences=prefs)
    except Exception as e:  # noqa: BLE001
        print(f"[parser] LLM failed ({e}); using keyword fallback")
        return _keyword_fallback(text)