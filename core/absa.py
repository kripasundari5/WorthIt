"""Aspect-based sentiment analysis.

Backends:
  "llm"     : batch to an LLM. Best quality, no GPU, costs money.
  "lexicon" : rule + lexicon. Free, offline, noisier. DEFAULT.

No fine-tuning path on purpose -- it is the only GPU-dependent part and the
first thing to cut. Train on Colab later and drop weights in models/.
"""
from __future__ import annotations

import functools
import json
import os
import re

from core.config import ANTHROPIC_API_KEY, ASPECTS, LLM_MODEL

BACKEND = os.getenv("ABSA_BACKEND", "lexicon")  # "llm" | "lexicon"


# --------------------------------------------------------------- keywords
ASPECT_KEYWORDS = {
    "performance": [
        "performance", "processor", "cpu", "ram", "speed", "fast", "slow",
        "lag", "lags", "laggy", "smooth", "gaming", "fps", "multitask",
        "multitasking", "hangs", "i3", "i5", "i7", "ryzen", "ssd", "boot",
        "rendering", "editing",
    ],
    "battery_life": [
        "battery", "backup", "battery life", "battery backup",
        "power backup", "unplugged", "charge",
    ],
    "portability": [
        "weight", "lightweight", "light", "heavy", "portable", "portability",
        "carry", "slim", "thin", "bulky", "travel", "bag",
    ],
    "thermals": [
        "heat", "heats", "heating", "hot", "warm", "fan", "fans",
        "fan noise", "cooling", "overheat", "overheating", "thermal",
        "thermals", "temperature", "throttle", "throttling",
    ],
    "display": [
        "display", "screen", "brightness", "colour", "color", "resolution",
        "fhd", "refresh rate", "panel", "viewing", "dim", "glare", "nits",
    ],
    "build_quality": [
        "build", "plastic", "metal", "body", "hinge", "chassis", "finish",
        "durable", "durability", "flimsy", "sturdy", "premium",
    ],
    "value": [
        "value", "worth", "price", "money", "budget", "expensive",
        "cheap", "deal", "affordable", "vfm", "pricing",
    ],
}

# ------------------------------------------------------------- sentiment
# NOTE: words that are ALSO aspect keywords must NOT appear here, or the
# aspect scores itself positive just for being mentioned. "value", "worth",
# "premium" and "sturdy" were removed for exactly that reason.
POS = {
    "excellent", "great", "amazing", "good", "best", "superb", "fantastic",
    "love", "loved", "perfect", "impressive", "solid", "smooth", "crisp",
    "sharp", "bright", "strong", "reliable", "outstanding", "nice",
    "brilliant", "decent", "satisfied", "recommend", "recommended",
    "awesome", "happy", "lovely", "handy", "responsive", "super", "easy", "comfortable",
    "compact", "worthy", "fine", "okay",
}

NEG = {
    "bad", "poor", "terrible", "awful", "worst", "horrible", "laggy",
    "weak", "disappointing", "disappointed", "useless", "flimsy", "dull",
    "grainy", "noisy", "mediocre", "unusable", "fails", "issue", "issues",
    "problem", "problems", "hate", "waste", "pathetic", "regret", "worse",
    "lags", "hangs", "stuck", "defective", "refund", "low", "less",
    "drains", "drain", "draining", "drained", "overheats", "overheating",
    "heating", "heats", "heat", "throttle", "throttling", "dim", "bulky", "sweats",
    "loud", "sluggish", "slow", "broke", "broken", "faulty", "damaged",
}

NEGATORS = {
    "not", "no", "never", "isn't", "wasn't", "doesn't", "didn't", "don't",
    "dont", "cannot", "can't", "without", "hardly", "barely", "nothing",
    "none",
}

# Words whose polarity depends on the aspect. "fast" is good for
# performance, bad when it describes a battery emptying.
ASPECT_POLARITY_FLIP = {
    "battery_life": {"fast", "quickly", "quick", "rapidly", "soon"},
}

DRAIN_WORDS = ("drain", "drains", "draining", "drained", "dies", "die",
               "empty", "discharge", "discharges")


# ----------------------------------------------------------- tokenising
@functools.lru_cache(maxsize=None)
def _kw_pattern(keyword: str) -> re.Pattern:
    """Word-boundary matcher.

    Plain substring matching is badly wrong here: "thin" matches inside
    "within", "ports" inside "supports", "value" inside "valuable". Every
    one of those silently corrupts the aspect scores.
    """
    return re.compile(rf"\b{re.escape(keyword)}\b", re.I)


def _mentions(clause_low: str, keys) -> bool:
    return any(_kw_pattern(k).search(clause_low) for k in keys)


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


CLAUSE_SPLIT = re.compile(
    r"(?:^|\s+)except\s+|(?:^|\s+)apart from\s+|"
    r"\s+but\s+|\s+however\s+|\s+although\s+|\s+though\s+|"
    r"\s+whereas\s+|\s+while\s+|"
    r"\s+other than\s+|\s+only issue\s+|\s+downside\s+|,\s+|;\s+", re.I)


def _split_clauses(sentence: str) -> list[str]:
    """Split on contrastive markers.

    Critical: "performance is great but battery is poor" scored as ONE unit
    gives +1 and -1 cancelling to 0.0 for BOTH aspects. That failure is
    silent -- the pipeline runs, numbers appear, every score is meaningless.
    """
    parts = [c.strip() for c in CLAUSE_SPLIT.split(sentence) if c.strip()]
    return parts or [sentence]


def _clause_sentiment(clause: str) -> float | None:
    """Mean polarity of sentiment words, with a negation window."""
    words = re.findall(r"[a-z']+", clause.lower())
    if not words:
        return None

    score, hits = 0.0, 0
    for i, w in enumerate(words):
        val = 1.0 if w in POS else (-1.0 if w in NEG else 0.0)
        if val == 0.0:
            continue
        # Window of 8: "don't face any lag or issue" puts the negator far
        # from the sentiment word in Indian-English review phrasing.
        if any(n in words[max(0, i - 8): i] for n in NEGATORS):
            val = -val * 0.8
        score += val
        hits += 1

    if hits == 0:
        return None
    return max(-1.0, min(1.0, score / hits))


# backwards-compatible alias
_sentence_sentiment = _clause_sentiment


def extract_lexicon(text: str) -> list[tuple[str, float, str]]:
    """Return [(aspect, sentiment, evidence_span)], clause-level.

    One mention per aspect per review -- the first clause that discusses it
    wins. Prevents a single rambling review dominating a product's score.
    """
    out: list[tuple[str, float, str]] = []
    seen: set[str] = set()

    for sent in _split_sentences(text):
        for clause in _split_clauses(sent):
            low = clause.lower()
            sentiment = _clause_sentiment(clause)
            if sentiment is None:        # no sentiment words in this clause
                continue

            for aspect, keys in ASPECT_KEYWORDS.items():
                if aspect in seen:
                    continue
                if not _mentions(low, keys):
                    continue

                score = sentiment
                flip = ASPECT_POLARITY_FLIP.get(aspect, set())
                if flip and _mentions(low, flip) and _mentions(low, DRAIN_WORDS):
                    score = -abs(score)   # "battery draining fast" is bad

                out.append((aspect, float(score), clause[:300]))
                seen.add(aspect)

    return out


# ------------------------------------------------------------- LLM path
LLM_SYSTEM = f"""Extract aspect-level sentiment from laptop reviews.

Valid aspects: {", ".join(ASPECTS)}

For each review return every aspect actually discussed, with:
- sentiment from -1.0 (very negative) to 1.0 (very positive)
- evidence: the exact sentence, verbatim, max 200 chars

Return ONLY a JSON array, one object per input review, no fences:
[{{"i": 0, "mentions": [{{"aspect": "performance", "sentiment": 0.8,
   "evidence": "..."}}]}}]

If a review discusses no listed aspect, return an empty mentions array."""


def extract_llm_batch(texts: list[str]) -> list[list[tuple[str, float, str]]]:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    payload = "\n\n".join(f"[{i}] {t[:1500]}" for i, t in enumerate(texts))
    resp = client.messages.create(
        model=LLM_MODEL, max_tokens=4000, system=LLM_SYSTEM,
        messages=[{"role": "user", "content": payload}])
    raw = "".join(b.text for b in resp.content if b.type == "text")
    raw = re.sub(r"```(?:json)?|```", "", raw).strip()

    results: list[list[tuple[str, float, str]]] = [[] for _ in texts]
    try:
        for item in json.loads(raw):
            i = item.get("i")
            if i is None or i >= len(texts):
                continue
            for m in item.get("mentions", []):
                if m.get("aspect") in ASPECTS:
                    results[i].append((
                        m["aspect"], float(m.get("sentiment", 0.0)),
                        (m.get("evidence") or "")[:300]))
    except json.JSONDecodeError as e:
        print(f"[absa] LLM JSON parse failed ({e}); falling back")
        return [extract_lexicon(t) for t in texts]
    return results


def extract_batch(texts: list[str]) -> list[list[tuple[str, float, str]]]:
    if BACKEND == "llm" and ANTHROPIC_API_KEY:
        try:
            return extract_llm_batch(texts)
        except Exception as e:  # noqa: BLE001
            print(f"[absa] LLM backend failed ({e}); using lexicon")
    return [extract_lexicon(t) for t in texts]